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

PBS_HOST = os.environ.get('PBS_HOST', 'https://localhost:8007')
PBS_TOKEN_NAME = os.environ.get('PBS_TOKEN_NAME', 'root@pam!apitoken')
PBS_TOKEN_SECRET = os.environ.get('PBS_TOKEN_SECRET', '')
PBS_VERIFY_SSL = os.environ.get('PBS_VERIFY_SSL', 'false').lower() == 'true'

NETBOX_HOST = os.environ.get('NB_API_URL', 'http://localhost:8000')
NETBOX_TOKEN = os.environ.get('NB_API_TOKEN', '')

PBS_NODE_NAME = os.environ.get('PBS_NODE_NAME', 'pbs')

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
        self.nb = pynetbox.api(NETBOX_HOST, NETBOX_TOKEN)
        self.nb.http_session.verify = False
        self.pbs = PBSClient(PBS_HOST, PBS_TOKEN_NAME, PBS_TOKEN_SECRET, PBS_VERIFY_SSL)

    def get_or_create_obj(self, endpoint, name, extra_fields=None):
        slug = slugify(name)
        obj = endpoint.get(slug=slug) or endpoint.get(name=name)
        if not obj:
            data = {'name': name, 'slug': slug}
            if extra_fields: data.update(extra_fields)
            obj = endpoint.create(**data)
        return obj

    def sync(self):
        logger.info("Starting PBS sync for node: %s", PBS_NODE_NAME)

        # 1. 獲取 PBS 數據
        status = self.pbs.get(f"/api2/json/nodes/{PBS_NODE_NAME}/status")
        version_data = self.pbs.get("/api2/json/version") or {}
        if not status:
            logger.error("Cannot fetch status for PBS node '%s' — check host/credentials", PBS_NODE_NAME)
            return

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
            'name': PBS_NODE_NAME,
            'device_type': dt.id,
            'role': role.id,
            'site': site.id,
            'platform': platform.id,
            'status': 'active',
            'comments': comments,
            'custom_fields': {
                'host_cpu_cores': cpu_cores,  # 確保為 int
                'host_memory': mem_total,      # 假設此欄位為 Text
                'host_disk_size': disk_total,  # 假設此欄位為 Text
                'host_disk_free': disk_free    # 假設此欄位為 Text
            }
        }

        device = self.nb.dcim.devices.get(name=PBS_NODE_NAME)
        try:
            if device:
                device.update(device_data)
                logger.info("Updated device: %s", PBS_NODE_NAME)
            else:
                device = self.nb.dcim.devices.create(**device_data)
                logger.info("Created device: %s", PBS_NODE_NAME)
        except Exception as e:
            logger.warning("Device sync error (retrying without custom_fields): %s", e)
            device_data.pop('custom_fields')
            if device:
                device.update(device_data)
            else:
                device = self.nb.dcim.devices.create(**device_data)

        # 4. 同步網路並設置 Primary IP
        self.sync_networking(device)

    def sync_networking(self, device):
        logger.info("Syncing network config for %s", PBS_NODE_NAME)
        pbs_net = self.pbs.get(f"/api2/json/nodes/{PBS_NODE_NAME}/network")
        if not pbs_net:
            return

        api_host_ip = PBS_HOST.split('//')[-1].split(':')[0]
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
                if not nb_ip:
                    nb_ip = self.nb.ipam.ip_addresses.create(
                        address=cidr, status='active',
                        assigned_object_type='dcim.interface', assigned_object_id=nb_if.id
                    )
                else:
                    nb_ip.assigned_object_type = 'dcim.interface'
                    nb_ip.assigned_object_id = nb_if.id
                    nb_ip.save()

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
