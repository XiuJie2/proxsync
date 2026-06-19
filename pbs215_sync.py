#!/usr/bin/env python3
"""
pbs-sync: 同步 PBS 到 NetBox (修正整數類型衝突版本)
"""

import logging
import os
import re
import urllib3
from datetime import datetime
from typing import Optional, Any

import pynetbox
import requests

logger = logging.getLogger(__name__)

# ============================================================================
# 配置部分
# ============================================================================

def _get_env(key, default=''):
    """Read env var at call time (not import time) so RQ workers pick up per-job values."""
    return os.environ.get(key, default)

# ============================================================================
# 工具函數
# ============================================================================

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')[:50]

def disk_format_size(bytes_val: int) -> str:
    """轉換為 GB 字串"""
    return f"{round(bytes_val / (1024**4), 2)} TB"

def mem_format_size(bytes_val: int) -> str:
    """轉換為 GB 字串"""
    return f"{round(bytes_val / (1024**3), 2)} GB"

# ============================================================================
# PBS API 客户端
# ============================================================================

class PBSClient:
    def __init__(self, host: str, token_name: str, token_secret: str, verify_ssl: bool = False):
        self.host = host.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"PBSAPIToken={token_name}:{token_secret}",
            "Accept": "application/json"
        })
        self.verify_ssl = verify_ssl

    def get(self, endpoint: str) -> Optional[Any]:
        try:
            resp = self.session.get(f"{self.host}{endpoint}", verify=self.verify_ssl, timeout=15)
            if resp.status_code == 200:
                return resp.json().get('data')
            return None
        except: return None

# ============================================================================
# NetBox 同步器
# ============================================================================

class PBSToNetBoxSync:
    def __init__(self):
        pbs_host = _get_env('PBS_HOST', 'https://localhost:8007')
        pbs_token_name = _get_env('PBS_TOKEN_NAME', 'root@pam!apitoken')
        pbs_token_secret = _get_env('PBS_TOKEN_SECRET', '')
        pbs_verify_ssl = _get_env('PBS_VERIFY_SSL', 'false').lower() == 'true'
        netbox_host = _get_env('NB_API_URL', 'http://localhost:8000')
        netbox_token = _get_env('NB_API_TOKEN', '')

        self.nb = pynetbox.api(netbox_host, netbox_token)
        self.nb.http_session.verify = False
        self.pbs = PBSClient(pbs_host, pbs_token_name, pbs_token_secret, pbs_verify_ssl)

    def get_or_create_obj(self, endpoint, name, extra_fields=None):
        slug = slugify(name)
        obj = endpoint.get(slug=slug) or endpoint.get(name=name)
        if not obj:
            data = {'name': name, 'slug': slug}
            if extra_fields: data.update(extra_fields)
            obj = endpoint.create(**data)
        return obj

    def sync(self):
        node_name = _get_env('PBS_NODE_NAME', 'pbs')
        logger.info("Starting PBS sync for node: %s", node_name)

        # 1. 獲取 PBS 數據
        status = self.pbs.get(f"/api2/json/nodes/{node_name}/status")
        version_data = self.pbs.get("/api2/json/version") or {}
        if not status:
            raise RuntimeError(
                f"Cannot fetch status for PBS node '{node_name}' "
                f"(host={_get_env('PBS_HOST')}) — check connectivity or pbs_node_name setting"
            )

        pbs_ver = version_data.get('version', '4.x')
        cpu_cores = int(status.get('cpuinfo', {}).get('cpus', 0))
        mem_total = mem_format_size(status.get('memory', {}).get('total', 0))
        disk_total = disk_format_size(status.get('root', {}).get('total', 0))
        disk_free = disk_format_size(status.get('root', {}).get('avail', 0))

        # 2. 獲取 NetBox 基礎物件
        site = self.get_or_create_obj(self.nb.dcim.sites, "Main Datacenter")
        manu = self.get_or_create_obj(self.nb.dcim.manufacturers, "Proxmox")
        role = self.get_or_create_obj(self.nb.dcim.device_roles, "Backup Server", {'color': '9e9e9e'})
        platform = self.get_or_create_obj(self.nb.dcim.platforms, "Proxmox Backup Server")
        
        model_name = "PBS Server"
        slug = slugify(model_name)
        dt = self.nb.dcim.device_types.get(slug=slug) or self.nb.dcim.device_types.get(model=model_name)
        if not dt:
            dt = self.nb.dcim.device_types.create(model=model_name, slug=slug, manufacturer=manu.id)

        # 3. 同步設備資訊
        comments = (
            f"### PBS 系統資訊\n"
            f"- **Version**: {pbs_ver}\n"
            f"- **CPU Cores**: {cpu_cores}\n"
            f"- **Memory**: {mem_total}\n"
            f"- **Disk Size**: {disk_total}\n"
            f"- **Disk Free**: {disk_free}\n"
            f"- **Last Sync**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        device_data = {
            'name': node_name,
            'device_type': dt.id,
            'role': role.id,
            'site': site.id,
            'platform': platform.id,
            'status': 'active',
            'comments': comments,
            'custom_fields': {
                'host_cpu_cores': cpu_cores,
                'host_memory': mem_total,
                'host_disk_size': disk_total,
                'host_disk_free': disk_free,
            }
        }

        device = self.nb.dcim.devices.get(name=node_name)
        try:
            if device:
                device.update(device_data)
                logger.info("Updated device: %s", node_name)
            else:
                device = self.nb.dcim.devices.create(**device_data)
                logger.info("Created device: %s", node_name)
        except Exception as e:
            logger.warning("Device sync error (retrying without custom_fields): %s", e)
            device_data.pop('custom_fields')
            if device:
                device.update(device_data)
            else:
                device = self.nb.dcim.devices.create(**device_data)

        # 4. 同步網路並設置 Primary IP
        self.sync_networking(device, node_name)

    def sync_networking(self, device, node_name=None):
        if node_name is None:
            node_name = _get_env('PBS_NODE_NAME', 'pbs')
        logger.info("Syncing network config for %s", node_name)
        pbs_net = self.pbs.get(f"/api2/json/nodes/{node_name}/network")
        if not pbs_net:
            return

        api_host_ip = _get_env('PBS_HOST', '').split('//')[-1].split(':')[0]
        primary_ip_candidate = None

        for item in pbs_net:
            iface_name = item.get('iface')
            if not iface_name or item.get('type') not in ['eth', 'bridge', 'bond']:
                continue

            mac = item.get('address', '').lower()
            cidr = item.get('cidr')

            # 接口
            nb_if = self.nb.dcim.interfaces.get(device_id=device.id, name=iface_name)
            if not nb_if:
                nb_if = self.nb.dcim.interfaces.create(
                    device=device.id, name=iface_name, type='1000base-t', mac_address=mac or None
                )
            elif mac and nb_if.mac_address != mac:
                nb_if.mac_address = mac
                nb_if.save()

            # IP
            if cidr:
                nb_ip = self.nb.ipam.ip_addresses.get(address=cidr)
                assigned_to_this_device = False
                if not nb_ip:
                    nb_ip = self.nb.ipam.ip_addresses.create(
                        address=cidr, status='active',
                        assigned_object_type='dcim.interface', assigned_object_id=nb_if.id
                    )
                    assigned_to_this_device = True
                else:
                    already_on_this_iface = (
                        getattr(nb_ip, 'assigned_object_id', None) == nb_if.id
                        and getattr(nb_ip, 'assigned_object_type', '') == 'dcim.interface'
                    )
                    if already_on_this_iface:
                        assigned_to_this_device = True
                    else:
                        try:
                            nb_ip.assigned_object_type = 'dcim.interface'
                            nb_ip.assigned_object_id = nb_if.id
                            nb_ip.save()
                            assigned_to_this_device = True
                        except Exception as e:
                            if 'primary' in str(e).lower() or '400' in str(e):
                                logger.warning(
                                    "IP %s is primary IP elsewhere, skipping reassignment", cidr
                                )
                            else:
                                raise

                # Only use as primary candidate if actually assigned to this device
                if assigned_to_this_device:
                    if not primary_ip_candidate or (api_host_ip in cidr):
                        primary_ip_candidate = nb_ip

        if primary_ip_candidate:
            device.primary_ip4 = primary_ip_candidate.id
            device.save()
            logger.info("Set primary IPv4: %s", primary_ip_candidate.address)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    PBSToNetBoxSync().sync()
