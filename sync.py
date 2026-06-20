"""
netbox-pve-sync: 同步 Proxmox VE 到 NetBox
優化版 - 使用預加載和快取來提高效能，包含 Telegram 通知
增強版 - 支援狀態持久化、節點監控、配置漂移檢測、增量同步
"""

import os
import sys
import time
import json
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple, Set
import urllib3
import pynetbox
from proxmoxer import ProxmoxAPI, ResourceException
from requests.exceptions import ReadTimeout, ConnectionError
import requests

try:
    from state_db import StateDB, compute_config_hash
    from config import get_config
    ENHANCED_MODE = True
except ImportError:
    def compute_config_hash(*args, **kwargs) -> str:
        return "fallback_hash"
    ENHANCED_MODE = False
    StateDB = None
    get_config = None


class OptimizedPVEToNetBoxSync:
    """優化的 PVE 到 NetBox 同步器"""

    def __init__(self, job_id=None):
        """初始化"""
        self.pve_api = None
        self.nb_api = None
        self.custom_fields_created = False
        self.job_id = job_id

        self.stats = {
            'nodes_offline': 0,
            'config_drifts_detected': 0,
            'tag_changes': 0,
            'resources_alert': 0,
            'total_vms': 0,
            'success_vms': 0,
            'elapsed_time': 0
        }

        self.enhanced_mode = ENHANCED_MODE
        self.state_db = None
        self.config = None
        self.cluster_name = "default"
        self.monitoring_config = {}
        self.sync_config = {}
        self._newly_created_nodes: set = set()
        self._known_vmids: dict = {}  # populated at start of sync_pve_virtual_machines

        if self.enhanced_mode:
            try:
                self.config = get_config()
                clusters = self.config.get_cluster_configs()
                if clusters:
                    self.cluster_config = clusters[0]
                    self.cluster_name = self.cluster_config.get('name', 'default')
                    state_db_config = self.config.get_state_db_config()
                    self.state_db = StateDB(state_db_config.get('path', '/var/lib/pve-sync/state.db'))
                    self.monitoring_config = self.config.get_monitoring_config()
                    self.sync_config = self.config.get_sync_config()
                    print(f"✓ 增強模式已啟用: 集群={self.cluster_name}, 狀態DB={state_db_config.get('path')}")
                else:
                    print("⚠ 未找到集群配置，回退到基礎模式")
                    self.enhanced_mode = False
            except Exception as e:
                print(f"⚠ 增強模式初始化失敗: {e}，回退到基礎模式")
                self.enhanced_mode = False

        # Telegram 配置
        if self.enhanced_mode and self.config:
            telegram_config = self.config.get_telegram_config()
            if telegram_config:
                self.telegram_bot_token = telegram_config.get('bot_token')
                self.telegram_chat_id = telegram_config.get('chat_id')
            else:
                self.telegram_bot_token = None
                self.telegram_chat_id = None
        else:
            self.telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
            self.telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')

        # NetBox 快取
        self.nb_cache = {
            'devices': {},
            'virtual_machines': {},
            'virtual_machines_by_serial': {},
            'virtual_machines_by_name': {},
            'vm_interfaces': {},
            'device_interfaces': {},
            'mac_addresses': {},
            'prefixes': {},
            'ip_addresses': {},
            'vlans': {},
            'vm_disks': {},
            'tags': {},
            'platforms': {},
            'roles': {},
            'clusters': {},
            'sites': {},
            'manufacturers': {},
            'device_types': {},
            'device_roles': {},
            'cluster_types': {},
        }

        self.pve_cache = {
            'nodes': [],
            'vms_by_node': {},
            'pools': {},
            'node_networks': {},
        }

        self.error_log = []

    # ---------- Telegram ----------
    def send_telegram_notification(self, message: str):
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {'chat_id': self.telegram_chat_id, 'text': message, 'parse_mode': 'HTML'}
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                print(f"✓ Telegram 通知已發送")
                return True
            else:
                print(f"✗ Telegram 通知發送失敗: {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ 發送 Telegram 通知失敗: {e}")
            return False

    def log_ip_conflict_error(self, vm_name: str, ip_address: str, error_message: str):
        error_info = {
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
            'vm_name': vm_name,
            'ip_address': ip_address,
            'error': error_message
        }
        self.error_log.append(error_info)
        message = f"""
🚨 <b>PVE-NetBox 同步 IP 衝突警告</b>

📅 時間: {error_info['timestamp']}
🖥️ 虛擬機: {vm_name}
🌐 IP 位址: {ip_address}
❌ 錯誤: {error_message}

⚠️ 需要手動處理
"""
        self.send_telegram_notification(message)
        print(f"📧 已發送 IP 衝突通知: {vm_name} - {ip_address}")

    def send_enhanced_summary(self):
        if not hasattr(self, 'stats'):
            return
        total_count = self.stats.get('total_vms', 0)
        success_count = self.stats.get('success_vms', 0)
        error_count = total_count - success_count
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0
        elapsed = self.stats.get('elapsed_time', 0)
        message = f"""
📊 <b>PVE-NetBox 同步報告</b>

📅 時間: {time.strftime('%Y-%m-%d %H:%M:%S')}
🏷️ 集群: {self.cluster_name}
⏱️ 耗時: {elapsed:.1f}秒

✅ 成功: {success_count} 台 VM
📊 總計: {total_count} 台 VM
❌ 失敗: {error_count} 台
📈 成功率: {success_rate:.1f}%

"""
        extras = []
        if self.stats.get('nodes_offline', 0) > 0:
            extras.append(f"🚨 節點離線: {self.stats['nodes_offline']}")
        if self.stats.get('config_drifts_detected', 0) > 0:
            extras.append(f"🔄 配置變更: {self.stats['config_drifts_detected']}")
        if self.stats.get('tag_changes', 0) > 0:
            extras.append(f"🏷️ 標籤變更: {self.stats['tag_changes']}")
        if self.stats.get('resources_alert', 0) > 0:
            extras.append(f"⚠️ 資源告警: {self.stats['resources_alert']}")
        if extras:
            message += "\n🔍 檢測發現:\n" + "\n".join(extras)
        if self.error_log:
            message += f"\n⚠️ <b>需處理的錯誤:</b>\n"
            for error in self.error_log[:5]:
                message += f"• {error['vm_name']} - {error['ip_address']}\n"
            if len(self.error_log) > 5:
                message += f"• ... 還有 {len(self.error_log) - 5} 個錯誤\n"
        self.send_telegram_notification(message)

    # ---------- API 連接 ----------
    def connect_pve(self) -> bool:
        max_retries = 3
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                self.pve_api = ProxmoxAPI(
                    host=os.environ['PVE_API_HOST'],
                    user=os.environ['PVE_API_USER'],
                    token_name=os.environ['PVE_API_TOKEN'],
                    token_value=os.environ['PVE_API_SECRET'],
                    verify_ssl=os.getenv('PVE_API_VERIFY_SSL', 'false').lower() == 'true',
                    timeout=30,
                )
                self.pve_api.nodes.get()
                print("✓ PVE API 連接成功")
                return True
            except (ReadTimeout, ConnectionError) as e:
                print(f"PVE API 連接失敗 (嘗試 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        raise RuntimeError(
            f"PVE API 無法連線 (host={os.environ.get('PVE_API_HOST')})，"
            f"已重試 {max_retries} 次仍失敗，請確認網路連線與防火牆設定"
        )

    def connect_netbox(self) -> bool:
        try:
            self.nb_api = pynetbox.api(
                url=os.environ['NB_API_URL'],
                token=os.environ['NB_API_TOKEN'],
            )
            self.nb_api.http_session.verify = False
            self.nb_api.http_session.timeout = 30
            count = self.nb_api.dcim.devices.count()
            print(f"✓ NetBox API 連接成功 (現有設備數: {count})")
            return True
        except Exception as e:
            print(f"✗ NetBox API 連接失敗: {e}")
            return False

    # ---------- NetBox 預加載 ----------
    def load_all_netbox_objects(self):
        print("\n預加載 NetBox 物件...")
        start_time = time.time()
        for device in self.nb_api.dcim.devices.all():
            self.nb_cache['devices'][device.name.lower()] = device
            dev_cluster_id = device.cluster.id if device.cluster else 'no-cluster'
            self.nb_cache['devices'][f"{device.name.lower()}::{dev_cluster_id}"] = device
        for vm in self.nb_api.virtualization.virtual_machines.all():
            self.nb_cache['virtual_machines'][vm.id] = vm
            if vm.serial:
                cluster_id = vm.cluster.id if vm.cluster else 'no-cluster'
                # Key includes cluster_id so same vmid from different PVE clusters
                # are stored separately and don't overwrite each other.
                serial_key = f"{vm.serial}::{cluster_id}"
                self.nb_cache['virtual_machines_by_serial'][serial_key] = vm
            cluster_id = vm.cluster.id if vm.cluster else 'no-cluster'
            key = f"{vm.name.lower()}::{cluster_id}"
            self.nb_cache['virtual_machines_by_name'][key] = vm
        for iface in self.nb_api.virtualization.interfaces.all():
            vm_id = iface.virtual_machine.id
            self.nb_cache['vm_interfaces'].setdefault(vm_id, {})[iface.name] = iface
        for iface in self.nb_api.dcim.interfaces.all():
            device_id = iface.device.id
            self.nb_cache['device_interfaces'].setdefault(device_id, {})[iface.name] = iface
        for mac in self.nb_api.dcim.mac_addresses.all():
            if mac.mac_address:
                self.nb_cache['mac_addresses'][mac.mac_address.lower()] = mac
        for prefix in self.nb_api.ipam.prefixes.all():
            self.nb_cache['prefixes'][prefix.prefix] = prefix
        for ip_addr in self.nb_api.ipam.ip_addresses.all():
            self.nb_cache['ip_addresses'][ip_addr.address] = ip_addr
        for vlan in self.nb_api.ipam.vlans.all():
            self.nb_cache['vlans'][str(vlan.vid)] = vlan
        for disk in self.nb_api.virtualization.virtual_disks.all():
            vm_id = disk.virtual_machine.id
            self.nb_cache['vm_disks'].setdefault(vm_id, {})[disk.name] = disk
        for tag in self.nb_api.extras.tags.all():
            self.nb_cache['tags'][tag.name] = tag
        for platform in self.nb_api.dcim.platforms.all():
            self.nb_cache['platforms'][platform.name.lower()] = platform
        for role in self.nb_api.dcim.device_roles.all():
            self.nb_cache['roles'][role.name.lower()] = role
        for cluster in self.nb_api.virtualization.clusters.all():
            self.nb_cache['clusters'][str(cluster.id)] = cluster
        for site in self.nb_api.dcim.sites.all():
            self.nb_cache['sites'][site.name.lower()] = site
        for manufacturer in self.nb_api.dcim.manufacturers.all():
            self.nb_cache['manufacturers'][manufacturer.name.lower()] = manufacturer
        for device_type in self.nb_api.dcim.device_types.all():
            self.nb_cache['device_types'][device_type.model.lower()] = device_type
        for device_role in self.nb_api.dcim.device_roles.all():
            self.nb_cache['device_roles'][device_role.name.lower()] = device_role
        for cluster_type in self.nb_api.virtualization.cluster_types.all():
            self.nb_cache['cluster_types'][cluster_type.name.lower()] = cluster_type
        elapsed = time.time() - start_time
        print(f"✓ 預加載完成，耗時 {elapsed:.2f} 秒")
        print(f"  設備: {len(self.nb_cache['devices'])} 個")
        print(f"  虛擬機: {len(self.nb_cache['virtual_machines'])} 個")
        print(f"  標籤: {len(self.nb_cache['tags'])} 個")
        print(f"  角色: {len(self.nb_cache['roles'])} 個")

    # ---------- PVE 數據加載 ----------
    def load_pve_data(self):
        print("\n加載 PVE 數據...")
        start_time = time.time()
        try:
            self.pve_cache['nodes'] = self.pve_api.nodes.get()
        except Exception as e:
            print(f"  加載節點失敗: {e}")
            self.pve_cache['nodes'] = []
        try:
            pools = self.pve_api.pools.get()
            for pool in pools:
                pool_id = pool['poolid']
                try:
                    pool_detail = self.pve_api.pools(pool_id).get()
                    members = []
                    for member in pool_detail.get('members', []):
                        if 'vmid' in member:
                            members.append({
                                'vmid': member['vmid'],
                                'type': member.get('type', 'qemu'),
                                'name': member.get('name', '')
                            })
                    self.pve_cache['pools'][pool_id] = {
                        'name': pool_id,
                        'comment': pool.get('comment', ''),
                        'members': members
                    }
                except Exception as e:
                    print(f"    獲取 pool {pool_id} 詳細資訊失敗: {e}")
        except Exception as e:
            print(f"  加載 Pools 失敗: {e}")
        for node in self.pve_cache['nodes']:
            node_name = node['node']
            try:
                qemu_vms = self.pve_api.nodes(node_name).qemu.get()
                lxc_vms = self.pve_api.nodes(node_name).lxc.get()
                all_vms = []
                for vm in qemu_vms:
                    vm['type'] = 'qemu'
                    vm['node'] = node_name
                    all_vms.append(vm)
                for vm in lxc_vms:
                    vm['type'] = 'lxc'
                    vm['node'] = node_name
                    all_vms.append(vm)
                self.pve_cache['vms_by_node'][node_name] = all_vms
                for vm in all_vms[:10]:
                    try:
                        if vm['type'] == 'qemu':
                            vm['config'] = self.pve_api.nodes(node_name).qemu(vm['vmid']).config.get()
                        else:
                            vm['config'] = self.pve_api.nodes(node_name).lxc(vm['vmid']).config.get()
                    except:
                        pass
            except Exception as e:
                print(f"  加載節點 {node_name} 的虛擬機失敗: {e}")
                self.pve_cache['vms_by_node'][node_name] = []
        elapsed = time.time() - start_time
        print(f"✓ PVE 數據加載完成，耗時 {elapsed:.2f} 秒")
        print(f"  節點: {len(self.pve_cache['nodes'])} 個")
        print(f"  Pools: {len(self.pve_cache['pools'])} 個")
        total_vms = sum(len(vms) for vms in self.pve_cache['vms_by_node'].values())
        print(f"  虛擬機: {total_vms} 個")

    # ---------- Custom Fields ----------
    def check_required_custom_fields(self):
        print("\n檢查 custom fields...")
        try:
            existing_fields = list(self.nb_api.extras.custom_fields.all())
            existing_names = [field.name for field in existing_fields]
            required_fields = [
                {'name': 'ha', 'label': 'Failover', 'type': 'boolean', 'content_types': ['virtualization.virtualmachine']},
                {'name': 'qemu_agent', 'label': 'QemuAgent', 'type': 'boolean', 'content_types': ['virtualization.virtualmachine']},
                {'name': 'search_domain', 'label': 'Search Domain', 'type': 'text', 'content_types': ['virtualization.virtualmachine']},
                {'name': 'vm_id', 'label': 'VM ID', 'type': 'integer', 'content_types': ['virtualization.virtualmachine']},
                {'name': 'replicated', 'label': 'Replicated', 'type': 'boolean', 'content_types': ['virtualization.virtualmachine']},
                {'name': 'machine_type', 'label': '機型', 'type': 'text', 'content_types': ['virtualization.virtualmachine']},
                {'name': 'host_cpu_cores', 'label': 'Host CPU Cores', 'type': 'integer', 'content_types': ['dcim.device']},
                {'name': 'host_memory', 'label': 'Host Memory', 'type': 'text', 'content_types': ['dcim.device']},
                {'name': 'host_disk_size', 'label': 'Host Disk Size', 'type': 'text', 'content_types': ['dcim.device']},
                {'name': 'host_disk_free', 'label': 'Host Disk Free', 'type': 'text', 'content_types': ['dcim.device']},
            ]
            missing_fields = [f for f in required_fields if f['name'] not in existing_names]
            if missing_fields:
                print(f"⚠ 缺少 {len(missing_fields)} 個 custom fields，相關欄位將略過（同步繼續）:")
                for field in missing_fields:
                    print(f"  - {field['name']} ({field['type']})")
                missing_list = "\n".join([f"- {f['name']}" for f in missing_fields])
                self.send_telegram_notification(
                    f"⚠️ <b>NetBox Custom Fields 缺失</b>\n\n以下欄位不存在，同步將略過這些欄位：\n\n{missing_list}\n\nNetBox 路徑: Extensions → Custom Fields"
                )
                self.custom_fields_created = False
            else:
                print("✓ 所有必要的 custom fields 都已存在")
                self.custom_fields_created = True
            return True
        except Exception as e:
            print(f"⚠ 檢查 custom fields 失敗: {e}，custom field 同步將略過")
            self.custom_fields_created = False
            return True

    # ---------- 輔助函數 ----------
    def get_vm_pool(self, vm_id: int, vm_type: str) -> Optional[str]:
        for pool_id, pool_info in self.pve_cache['pools'].items():
            for member in pool_info['members']:
                if member['vmid'] == vm_id and member['type'] == vm_type:
                    return pool_id
        return None

    def get_or_create_vm_role(self, role_name: str) -> Optional[int]:
        if not role_name:
            return None
        role_key = role_name.lower()
        if role_key in self.nb_cache['roles']:
            return self.nb_cache['roles'][role_key].id
        try:
            roles = list(self.nb_api.dcim.device_roles.filter(name=role_name))
            if roles:
                role = roles[0]
                self.nb_cache['roles'][role_key] = role
                return role.id
            slug = role_name.lower().replace(' ', '-').replace('(', '').replace(')', '').replace('/', '-')[:50]
            color_hash = hashlib.md5(role_name.encode()).hexdigest()[:6]
            role = self.nb_api.dcim.device_roles.create(
                name=role_name, slug=slug, color=color_hash, vm_role=True,
                description=f"Proxmox Pool: {role_name}"
            )
            self.nb_cache['roles'][role_key] = role
            return role.id
        except Exception as e:
            print(f"  建立虛擬機角色失敗 {role_name}: {e}")
            return None

    def get_or_create_site(self, site_name: str = "Main Datacenter") -> Optional[int]:
        site_key = site_name.lower()
        if site_key in self.nb_cache['sites']:
            return self.nb_cache['sites'][site_key].id
        try:
            sites = list(self.nb_api.dcim.sites.filter(name=site_name))
            if sites:
                site = sites[0]
                self.nb_cache['sites'][site_key] = site
                return site.id
            site = self.nb_api.dcim.sites.create(
                name=site_name, slug=site_name.lower().replace(' ', '-'), status='active'
            )
            self.nb_cache['sites'][site_key] = site
            return site.id
        except Exception as e:
            print(f"處理站點失敗: {e}")
            return None

    def get_or_create_manufacturer(self, name: str = "Generic") -> Optional[int]:
        key = name.lower()
        if key in self.nb_cache['manufacturers']:
            return self.nb_cache['manufacturers'][key].id
        try:
            manufacturers = list(self.nb_api.dcim.manufacturers.filter(name=name))
            if manufacturers:
                manufacturer = manufacturers[0]
                self.nb_cache['manufacturers'][key] = manufacturer
                return manufacturer.id
            slug = name.lower().replace(' ', '-').replace('/', '-')[:50]
            manufacturer = self.nb_api.dcim.manufacturers.create(name=name, slug=slug)
            self.nb_cache['manufacturers'][key] = manufacturer
            return manufacturer.id
        except Exception as e:
            print(f"  建立廠商失敗 {name}: {e}")
            return None

    def get_or_create_device_type(self, model_name: str = "Standard Server") -> Optional[int]:
        key = model_name.lower()
        if key in self.nb_cache['device_types']:
            return self.nb_cache['device_types'][key].id
        try:
            device_types = list(self.nb_api.dcim.device_types.filter(model=model_name))
            if device_types:
                device_type = device_types[0]
                self.nb_cache['device_types'][key] = device_type
                return device_type.id
            manufacturer_id = self.get_or_create_manufacturer("Generic")
            if not manufacturer_id:
                return None
            slug = model_name.lower().replace(' ', '-').replace('/', '-')[:50]
            device_type = self.nb_api.dcim.device_types.create(
                model=model_name, slug=slug, manufacturer=manufacturer_id,
                u_height=1, is_full_depth=False
            )
            self.nb_cache['device_types'][key] = device_type
            return device_type.id
        except Exception as e:
            print(f"  建立設備類型失敗 {model_name}: {e}")
            return None

    def get_or_create_device_role(self, role_name: str = "PVE") -> Optional[int]:
        key = role_name.lower()
        if key in self.nb_cache['device_roles']:
            return self.nb_cache['device_roles'][key].id
        try:
            roles = list(self.nb_api.dcim.device_roles.filter(name=role_name))
            if roles:
                role = roles[0]
                self.nb_cache['device_roles'][key] = role
                return role.id
            slug = role_name.lower().replace(' ', '-').replace('/', '-')[:50]
            role = self.nb_api.dcim.device_roles.create(
                name=role_name, slug=slug, color="c0c0c0", vm_role=False
            )
            self.nb_cache['device_roles'][key] = role
            return role.id
        except Exception as e:
            print(f"  建立設備角色失敗 {role_name}: {e}")
            return None

    def get_or_create_cluster_type(self, cluster_type_name: str = "Proxmox") -> Optional[int]:
        key = cluster_type_name.lower()
        if key in self.nb_cache['cluster_types']:
            return self.nb_cache['cluster_types'][key].id
        try:
            types = list(self.nb_api.virtualization.cluster_types.filter(name=cluster_type_name))
            if types:
                ct = types[0]
                self.nb_cache['cluster_types'][key] = ct
                return ct.id
            ct = self.nb_api.virtualization.cluster_types.create(
                name=cluster_type_name, slug=cluster_type_name.lower().replace(' ', '-'),
                description="Proxmox Virtual Environment Cluster"
            )
            self.nb_cache['cluster_types'][key] = ct
            return ct.id
        except Exception as e:
            print(f"處理集群類型失敗: {e}")
            return None

    def get_or_create_cluster(self, cluster_name: str, site_id: int, cluster_type_id: int) -> Optional[Dict]:
        try:
            clusters = list(self.nb_api.virtualization.clusters.filter(name=cluster_name))
            if clusters:
                cluster = clusters[0]
                return {'id': cluster.id, 'name': cluster.name}
            cluster = self.nb_api.virtualization.clusters.create(
                name=cluster_name, slug=cluster_name.lower().replace(' ', '-'),
                site=site_id, type=cluster_type_id
            )
            self.nb_cache['clusters'][str(cluster.id)] = cluster
            return {'id': cluster.id, 'name': cluster.name}
        except Exception as e:
            print(f"處理集群失敗: {e}")
            return None

    def check_qemu_agent(self, config: Dict[str, Any]) -> bool:
        if 'agent' in config:
            agent_value = str(config['agent']).strip()
            agent_parts = [part.strip() for part in agent_value.split(',')]
            for part in agent_parts:
                if part == '1' or part == 'enabled=1' or 'fstrim_cloned_disks=1' in part:
                    return True
        return False

    def parse_network_config(self, config_value: str) -> Dict:
        result = {}
        for item in config_value.split(','):
            if '=' in item:
                key, value = item.split('=', 1)
                result[key] = value
        return result

    def get_unique_vm_name(self, vm_name: str, vm_id: str, cluster_id: int) -> str:
        key = f"{vm_name.lower()}::{cluster_id}"
        existing_vm = self.nb_cache['virtual_machines_by_name'].get(key)
        if existing_vm:
            if existing_vm.serial and str(existing_vm.serial) == vm_id:
                return vm_name
            unique_name = f"{vm_name}-{vm_id}"
            print(f"  名稱衝突: {vm_name} 已存在，使用新名稱: {unique_name}")
            return unique_name
        for vm in self.nb_cache['virtual_machines_by_serial'].values():
            if vm.serial and str(vm.serial) == vm_id and vm.cluster and vm.cluster.id == cluster_id:
                if vm.name != vm_name:
                    new_key = f"{vm_name.lower()}::{cluster_id}"
                    if new_key not in self.nb_cache['virtual_machines_by_name']:
                        return vm_name
                    else:
                        unique_name = f"{vm_name}-{vm_id}"
                        print(f"  名稱衝突，使用新名稱: {unique_name}")
                        return unique_name
                return vm_name
        return vm_name

    # ---------- 節點硬體資訊 ----------
    def fetch_node_hardware_info(self, node_name: str) -> Dict[str, Any]:
        try:
            status = self.pve_api.nodes(node_name).status.get()
            cpuinfo = status.get('cpuinfo', {})
            memory = status.get('memory', {})
            rootfs = status.get('rootfs', {}) or status.get('root', {})
            disk_total = rootfs.get('total', 0)
            disk_used = rootfs.get('used', 0)
            disk_free = rootfs.get('avail', disk_total - disk_used)
            return {
                'cpu_cores': cpuinfo.get('cpus', 0),
                'memory_total': memory.get('total', 0),
                'disk_total': disk_total,
                'disk_free': disk_free,
            }
        except Exception as e:
            print(f"    獲取節點硬體資訊失敗 {node_name}: {e}")
            return {}

    # ---------- 設備介面獲取/建立 ----------
    def get_or_create_device_interface(self, device_id: int, iface_name: str, iface_type: str = 'eth',
                                       mac_address: str = None, enabled: bool = True) -> Optional[Any]:
        device_interfaces = self.nb_cache['device_interfaces'].get(device_id, {})
        if iface_name in device_interfaces:
            return device_interfaces[iface_name]
        try:
            iface_data = {
                'device': device_id, 'name': iface_name, 'enabled': enabled, 'type': iface_type
            }
            if mac_address:
                iface_data['mac_address'] = mac_address
            iface = self.nb_api.dcim.interfaces.create(**iface_data)
            self.nb_cache['device_interfaces'].setdefault(device_id, {})[iface_name] = iface
            return iface
        except Exception as e:
            print(f"      建立底層介面失敗 {iface_name}: {e}")
            return None

    # ---------- IP 分配（改進版） ----------
    def assign_ip_to_interface(self, interface, ip_address: str, dns_name: str = None, is_vm_interface: bool = False) -> Optional[Any]:
        try:
            if '/' not in ip_address:
                ip_with_prefix = f"{ip_address}/24"
            else:
                ip_with_prefix = ip_address

            assigned_object_type = 'virtualization.vminterface' if is_vm_interface else 'dcim.interface'

            # 檢查是否已存在
            existing_ip = self.nb_cache['ip_addresses'].get(ip_with_prefix)
            if not existing_ip:
                # 嘗試查找可能存在的同IP但不同前綴的位址
                ip_only = ip_with_prefix.split('/')[0]
                for addr, ip_obj in self.nb_cache['ip_addresses'].items():
                    if addr.startswith(ip_only + '/'):
                        existing_ip = ip_obj
                        break

            if existing_ip:
                # 更新已存在的IP
                existing_ip.address = ip_with_prefix  # 更新前綴長度
                existing_ip.assigned_object_type = assigned_object_type
                existing_ip.assigned_object_id = interface.id
                if dns_name:
                    existing_ip.dns_name = dns_name
                existing_ip.save()
                # 更新快取
                self.nb_cache['ip_addresses'][ip_with_prefix] = existing_ip
                return existing_ip

            # 建立新IP
            ip_data = {
                'address': ip_with_prefix,
                'assigned_object_type': assigned_object_type,
                'assigned_object_id': interface.id,
                'status': 'active'
            }
            if dns_name:
                ip_data['dns_name'] = dns_name

            ip_obj = self.nb_api.ipam.ip_addresses.create(**ip_data)
            self.nb_cache['ip_addresses'][ip_with_prefix] = ip_obj
            return ip_obj

        except Exception as e:
            error_msg = str(e)
            print(f"      分配 IP 位址失敗 {ip_address}: {error_msg}")
            if "Cannot reassign IP address while it is designated as the primary IP" in error_msg:
                vm_name = "Unknown"
                try:
                    if is_vm_interface:
                        vm_info = self.nb_api.virtualization.interfaces.get(interface.id)
                        if vm_info and vm_info.virtual_machine:
                            vm_name = vm_info.virtual_machine.name
                except:
                    pass
                self.log_ip_conflict_error(vm_name, ip_address, error_msg)
            return None

    # ---------- 節點網路介面同步 ----------
    def sync_node_network_interfaces(self, device, node_name: str, network_data: List[Dict]):
        print(f"    正在同步節點網路介面: {node_name}")
        device_id = device.id
        device_interfaces = self.nb_cache['device_interfaces'].get(device_id, {})
        for iface_data in network_data:
            iface_name = iface_data.get('iface')
            if not iface_name:
                continue
            iface_type = iface_data.get('type', '').lower()
            if iface_type not in ['eth', 'bridge', 'bond']:
                continue
            mac_address = iface_data.get('address', '').lower() or None
            enabled = iface_data.get('active', 1) == 1
            nb_iface_data = {
                'device': device_id, 'name': iface_name, 'mac_address': mac_address, 'enabled': enabled
            }
            if iface_type == 'eth':
                nb_iface_data['type'] = '1000base-t'
            elif iface_type == 'bridge':
                nb_iface_data['type'] = 'bridge'
                bridge_ports = iface_data.get('bridge_ports', '')
                if bridge_ports:
                    first_port = bridge_ports.split(',')[0].strip()
                    port_iface = self.get_or_create_device_interface(
                        device_id, first_port, iface_type='eth', mac_address=None, enabled=True
                    )
                    if port_iface:
                        nb_iface_data['bridge'] = port_iface.id
            elif iface_type == 'bond':
                nb_iface_data['type'] = 'bond'
            gateway = iface_data.get('gateway')
            if gateway:
                nb_iface_data['gateway'] = gateway
            if iface_name in device_interfaces:
                nb_iface = device_interfaces[iface_name]
                for key, value in nb_iface_data.items():
                    if key != 'device':
                        setattr(nb_iface, key, value)
                try:
                    nb_iface.save()
                except Exception as e:
                    print(f"      更新設備介面失敗 {iface_name}: {e}")
                    continue
            else:
                try:
                    nb_iface = self.nb_api.dcim.interfaces.create(**nb_iface_data)
                    self.nb_cache['device_interfaces'].setdefault(device_id, {})[iface_name] = nb_iface
                except Exception as e:
                    print(f"      建立設備介面失敗 {iface_name}: {e}")
                    continue
            cidr = iface_data.get('cidr')
            if cidr:
                self.assign_ip_to_interface(nb_iface, cidr, dns_name=f"{node_name}.local", is_vm_interface=False)

    # ---------- 節點同步 ----------
    def sync_pve_nodes_to_netbox(self) -> Tuple[bool, Dict[str, Any], Dict]:
        print("\n開始同步 PVE 節點...")
        settings = self.cluster_config.get('settings', {}) if self.cluster_config else {}
        site_name = settings.get('site_name', 'Main Datacenter')
        cluster_type_name = settings.get('cluster_type', 'Proxmox')
        netbox_cluster_name = settings.get('cluster_name', 'Proxmox Cluster')

        site_id = self.get_or_create_site(site_name)
        if not site_id:
            print("✗ 無法獲取或建立站點")
            return False, {}, {}
        cluster_type_id = self.get_or_create_cluster_type(cluster_type_name)
        if not cluster_type_id:
            print("✗ 無法獲取或建立集群類型")
            return False, {}, {}
        cluster = self.get_or_create_cluster(netbox_cluster_name, site_id, cluster_type_id)
        if not cluster:
            print("✗ 無法獲取或建立集群")
            return False, {}, {}
        print(f"  使用集群: {cluster['name']} (ID: {cluster['id']})")
        default_device_role = self.sync_config.get('default_node_role', 'PVE')
        default_device_type = self.sync_config.get('default_node_type', 'Standard Server')
        devices = {}
        success_count = 0
        for node in self.pve_cache['nodes']:
            pve_node_name = node['node']   # original PVE node name (used as devices dict key)
            node_name = pve_node_name      # may be overridden below if name collision
            node_status = node.get('status', 'unknown')
            # Prefer cluster-scoped lookup so same-named nodes in different clusters
            # don't collide (e.g. both clusters having a node named 'pve').
            # Also check the collision-fallback name ({node}-{cluster_name}) in case a
            # previous sync had to rename due to a (name, site) uniqueness conflict.
            collision_name = f"{node_name}-{self.cluster_name}".lower()
            device = (
                self.nb_cache['devices'].get(f"{node_name.lower()}::{cluster['id']}")
                or self.nb_cache['devices'].get(f"{collision_name}::{cluster['id']}")
                or self.nb_cache['devices'].get(node_name.lower())
            )
            # Reject match if it belongs to a different cluster
            if device and getattr(getattr(device, 'cluster', None), 'id', None) != cluster['id']:
                device = None
            if not device:
                print(f"  → 設備 {node_name} 不存在，嘗試自動建立...")
                device_role_id = self.get_or_create_device_role(default_device_role)
                if not device_role_id:
                    print(f"  ✗ 無法取得設備角色，跳過節點 {node_name}")
                    continue
                device_type_id = self.get_or_create_device_type(default_device_type)
                if not device_type_id:
                    print(f"  ✗ 無法取得設備類型，跳過節點 {node_name}")
                    continue
                try:
                    device = self.nb_api.dcim.devices.create(
                        name=node_name,
                        role=device_role_id,
                        device_type=device_type_id,
                        site=site_id,
                        status='active' if node_status == 'online' else 'offline',
                        cluster=cluster['id'],
                    )
                except Exception as e:
                    # Fallback: pynetbox may fail on NetBox 4.6+ 'location' bug;
                    # use Django ORM directly which bypasses the API validation quirk.
                    try:
                        from dcim.models import Device
                        create_name = node_name
                        try:
                            device_orm = Device.objects.create(
                                name=create_name,
                                role_id=device_role_id,
                                device_type_id=device_type_id,
                                site_id=site_id,
                                status='active' if node_status == 'online' else 'offline',
                                cluster_id=cluster['id'],
                            )
                        except Exception:
                            # (name, site) unique constraint — suffix with cluster name
                            create_name = f"{node_name}-{self.cluster_name}"
                            device_orm = Device.objects.create(
                                name=create_name,
                                role_id=device_role_id,
                                device_type_id=device_type_id,
                                site_id=site_id,
                                status='active' if node_status == 'online' else 'offline',
                                cluster_id=cluster['id'],
                            )
                            print(f"  ⚠ 名稱衝突，改用: {create_name}")
                        # Fetch back via API so we get a pynetbox object
                        device = self.nb_api.dcim.devices.get(device_orm.pk)
                        node_name = create_name  # update local var so cache uses correct key
                    except Exception as e2:
                        print(f"  ✗ 建立設備失敗 {node_name}: {e} / {e2}")
                        continue
                self.nb_cache['devices'][node_name.lower()] = device
                self.nb_cache['devices'][f"{node_name.lower()}::{cluster['id']}"] = device
                self._newly_created_nodes.add(node_name.lower())
                print(f"  ✓ 成功建立設備: {node_name} (ID: {device.id})")
            # 更新設備狀態（跳過剛建立的節點；正確比對 pynetbox Status 物件）
            if node_name.lower() not in self._newly_created_nodes:
                try:
                    old_val = getattr(device.status, 'value', str(device.status))
                    new_val = 'active' if node_status == 'online' else 'offline'
                    if old_val != new_val:
                        device.status = new_val
                        device.save()
                        print(f"  設備狀態更新: {node_name} {old_val} → {new_val}")
                except Exception as e:
                    print(f"  更新設備狀態失敗: {e}")
            # 同步硬體資訊
            hw_info = self.fetch_node_hardware_info(node_name)
            if hw_info:
                try:
                    comments = device.comments or ""
                    sync_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    hw_line = f"\n### 硬體資訊 (最後同步: {sync_time})\n- CPU核心: {hw_info['cpu_cores']}\n- 記憶體: {hw_info['memory_total'] / (1024**3):.1f} GB\n- 磁碟總容量: {hw_info['disk_total'] / (1024**3):.1f} GB\n- 磁碟可用: {hw_info['disk_free'] / (1024**3):.1f} GB"
                    if "### 硬體資訊" in comments:
                        parts = comments.split("### 硬體資訊")
                        comments = parts[0] + hw_line
                    else:
                        comments += hw_line
                    device.comments = comments
                    if self.custom_fields_created:
                        cf = dict(device.custom_fields or {})
                        cf.update({
                            'host_cpu_cores': hw_info['cpu_cores'],
                            'host_memory': f"{hw_info['memory_total'] / (1024**3):.1f} GB",
                            'host_disk_size': f"{hw_info['disk_total'] / (1024**3):.1f} GB",
                            'host_disk_free': f"{hw_info['disk_free'] / (1024**3):.1f} GB",
                        })
                        device.custom_fields = cf
                    device.save()
                except Exception as e:
                    print(f"  更新設備硬體資訊失敗 {node_name}: {e}")
            # 同步網路介面
            try:
                network_data = self.pve_api.nodes(pve_node_name).network.get()
                if network_data:
                    self.sync_node_network_interfaces(device, pve_node_name, network_data)
            except Exception as e:
                print(f"  獲取節點網路資訊失敗: {e}")
            # Always key by original PVE node name so VM sync can look up the device
            devices[pve_node_name.lower()] = device
            success_count += 1
        print(f"  節點同步完成: {success_count}/{len(self.pve_cache['nodes'])} 個節點")
        if success_count > 0:
            return True, devices, cluster
        else:
            return False, {}, {}

    # ---------- VM Agent 網路 ----------
    def get_vm_agent_network_info(self, node_name: str, vm_id: int, vm_type: str = 'qemu') -> Tuple[Dict[str, List[Dict]], Dict[str, str]]:
        try:
            if vm_type == 'qemu':
                interfaces = self.pve_api.nodes(node_name).qemu(vm_id).agent('network-get-interfaces').get()
            else:
                return {}, {}
            interface_data = {}
            mac_to_interface = {}
            for iface in interfaces.get('result', []):
                if 'name' in iface and 'hardware-address' in iface:
                    iface_name = iface['name']
                    mac_address = iface['hardware-address'].lower()
                    mac_to_interface[mac_address] = iface_name
                    interface_data[iface_name] = iface.get('ip-addresses', [])
            return interface_data, mac_to_interface
        except ResourceException as e:
            if "is not running" in str(e):
                pass
        except Exception:
            pass
        return {}, {}

    # ---------- VM 介面處理（修復橋接ID） ----------
    def process_vm_interfaces(self, vm, vm_config: Dict, agent_interfaces: Dict, mac_to_interface: Dict,
                              device) -> Tuple[int, Optional[Any], List[Dict]]:
        interface_count = 0
        primary_ip = None
        interfaces_data = []
        for config_key, config_value in vm_config.items():
            if not config_key.startswith('net'):
                continue
            interface_count += 1
            try:
                config = self.parse_network_config(config_value)
                mac_address = None
                for model in ['virtio', 'e1000', 'vmxnet3', 'rtl8139']:
                    if model in config:
                        mac_address = config[model]
                        break
                vm_interfaces = self.nb_cache['vm_interfaces'].get(vm.id, {})
                bridge_name = config.get('bridge', '')
                bridge_iface_id = None
                if bridge_name:
                    # 獲取或建立設備上的 bridge 介面（而非底層連接埠）
                    bridge_iface = self.get_or_create_device_interface(
                        device.id, bridge_name, iface_type='bridge', mac_address=None, enabled=True
                    )
                    if bridge_iface:
                        bridge_iface_id = bridge_iface.id
                    else:
                        print(f"      警告: 無法獲取設備 {device.name} 的橋接介面 {bridge_name}")
                if config_key in vm_interfaces:
                    vm_interface = vm_interfaces[config_key]
                    if mac_address:
                        vm_interface.mac_address = mac_address
                    if bridge_iface_id:
                        vm_interface.bridge = bridge_iface_id
                    vm_interface.save()
                else:
                    iface_create_data = {
                        'virtual_machine': vm.id, 'name': config_key, 'enabled': True
                    }
                    if mac_address:
                        iface_create_data['mac_address'] = mac_address
                    if bridge_iface_id:
                        iface_create_data['bridge'] = bridge_iface_id
                    vm_interface = self.nb_api.virtualization.interfaces.create(**iface_create_data)
                    self.nb_cache['vm_interfaces'].setdefault(vm.id, {})[config_key] = vm_interface
                iface_data = {
                    'name': config_key, 'mac_address': mac_address or '', 'bridge': bridge_name
                }
                interfaces_data.append(iface_data)
                agent_iface_name = mac_to_interface.get(mac_address.lower()) if mac_address else None
                if agent_iface_name and agent_iface_name in agent_interfaces:
                    ip_addresses = agent_interfaces[agent_iface_name]
                    for ip_info in ip_addresses:
                        if ip_info['ip-address-type'] == 'ipv4' and not ip_info['ip-address'].startswith('127.'):
                            ip_addr = ip_info['ip-address']
                            prefix_len = ip_info['prefix']
                            full_addr = f"{ip_addr}/{prefix_len}"
                            ip_obj = self.assign_ip_to_interface(
                                vm_interface, full_addr, f"{vm.name}.local", is_vm_interface=True
                            )
                            if ip_obj and not primary_ip:
                                primary_ip = ip_obj
            except Exception as e:
                print(f"    處理介面失敗 {config_key}: {e}")
        return interface_count, primary_ip, interfaces_data

    # ---------- VM 磁碟處理 ----------
    def process_vm_disks(self, vm, vm_config: Dict) -> Tuple[int, int]:
        disk_count = 0
        disk_size = 0
        for config_key, config_value in vm_config.items():
            if config_key.startswith(('scsi', 'virtio', 'sata', 'ide', 'efidisk', 'rootfs')):
                if 'media=cdrom' not in str(config_value):
                    success, size_mb = self.create_virtual_disk(vm, config_key, config_value)
                    if success:
                        disk_count += 1
                        disk_size += size_mb
        return disk_count, disk_size

    def create_virtual_disk(self, vm, disk_name: str, disk_config: str) -> Tuple[bool, int]:
        try:
            config = self.parse_network_config(disk_config)
            size_str = config.get('size', '0')
            size_mb = 0
            try:
                if size_str.endswith('G'):
                    size_mb = int(size_str[:-1]) * 1024
                elif size_str.endswith('T'):
                    size_mb = int(size_str[:-1]) * 1024 * 1024
                elif size_str.endswith('M'):
                    size_mb = int(size_str[:-1])
                elif size_str.endswith('K'):
                    size_mb = int(size_str[:-1]) // 1024
                else:
                    size_mb = int(size_str) // (1024 * 1024)
            except (ValueError, AttributeError):
                pass
            if size_mb <= 0:
                return False, 0
            vm_disks = self.nb_cache['vm_disks'].get(vm.id, {})
            if disk_name in vm_disks:
                disk = vm_disks[disk_name]
                disk.size = size_mb
                disk.save()
            else:
                disk = self.nb_api.virtualization.virtual_disks.create(
                    virtual_machine=vm.id, name=disk_name, size=size_mb,
                    description=f"Proxmox disk: {disk_name}"
                )
                self.nb_cache['vm_disks'].setdefault(vm.id, {})[disk_name] = disk
            return True, size_mb
        except Exception as e:
            print(f"    建立虛擬磁碟失敗 {disk_name}: {e}")
            return False, 0

    # ---------- 增量同步相關 ----------

    def _parse_disk_summary(self, vm_config: Dict[str, Any]) -> Dict[str, str]:
        """從 vm_config 提取磁碟 key → size 對應表。"""
        import re
        disks = {}
        for key, value in vm_config.items():
            if key.startswith(('scsi', 'virtio', 'ide', 'sata', 'efidisk', 'tpmstate')):
                val_str = str(value)
                m = re.search(r'size=([^,]+)', val_str)
                disks[key] = m.group(1) if m else val_str[:80]
        return disks

    def _write_drift_event(self, vm_name: str, vmid: int, drift_type: str,
                           field_name: str, old_value: str, new_value: str,
                           notified: bool = False):
        """Write a PveDriftEvent record via Django ORM. No-op outside Django context."""
        try:
            from pve_sync_plugin.models import PveDriftEvent
            kwargs = dict(
                vm_name=vm_name,
                vmid=vmid,
                cluster_name=self.cluster_name,
                drift_type=drift_type,
                field_name=field_name,
                old_value=str(old_value),
                new_value=str(new_value),
                notified_telegram=notified,
            )
            if self.job_id:
                kwargs['sync_job_id'] = self.job_id
            PveDriftEvent.objects.create(**kwargs)
        except Exception as e:
            print(f"  ⚠ 無法寫入漂移事件記錄: {e}")

    def detect_new_vm(self, vm_id: int, vm_name: str, node_name: str):
        """若此 vmid 在先前同步中不存在（但叢集有先前記錄），視為新增 VM。"""
        if not self.enhanced_mode or not self.state_db:
            return
        if not self._known_vmids:
            return  # 首次同步，無先前記錄，不觸發
        if self.state_db.get_last_vm_config(vm_id, self.cluster_name):
            return  # 已有記錄，不是新增
        print(f"🆕 VM {vm_name} 新增偵測 (ID: {vm_id}, 節點: {node_name})")
        self.stats['config_drifts_detected'] += 1
        new_msg = (
            f"🆕 <b>VM 新增偵測</b>\n\n"
            f"🖥️ 名稱: <b>{vm_name}</b> (ID: {vm_id})\n"
            f"🔀 叢集: {self.cluster_name}\n"
            f"📌 節點: <code>{node_name}</code>\n"
            f"📅 時間: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.send_telegram_notification(new_msg)
        self._write_drift_event(vm_name, vm_id, 'vm_created', 'vmid', '', str(vm_id), notified=True)

    def detect_deleted_vms(self, seen_vmids: set):
        """比對先前已知 vmid 與本次同步的 vmid，偵測被刪除的 VM。"""
        if not self.enhanced_mode or not self.state_db:
            return
        if not self._known_vmids:
            return
        deleted_vmids = set(self._known_vmids.keys()) - seen_vmids
        if not deleted_vmids:
            return
        for vmid in deleted_vmids:
            info = self._known_vmids[vmid]
            vm_name = info.get('vm_name') or f"VM-{vmid}"
            node_name = info.get('node') or 'unknown'
            # 避免重複通知：若已有此 vmid 的 vm_deleted 記錄則跳過
            try:
                from pve_sync_plugin.models import PveDriftEvent
                if PveDriftEvent.objects.filter(
                    vmid=vmid, cluster_name=self.cluster_name, drift_type='vm_deleted'
                ).exists():
                    continue
            except Exception:
                pass
            print(f"🗑️ VM {vm_name} 刪除偵測 (ID: {vmid}, 上次節點: {node_name})")
            self.stats['config_drifts_detected'] += 1
            del_msg = (
                f"🗑️ <b>VM 刪除偵測</b>\n\n"
                f"🖥️ 名稱: <b>{vm_name}</b> (ID: {vmid})\n"
                f"🔀 叢集: {self.cluster_name}\n"
                f"📌 上次節點: <code>{node_name}</code>\n"
                f"📅 時間: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"⚠️ 此 VM 已從 Proxmox 中移除。"
            )
            self.send_telegram_notification(del_msg)
            self._write_drift_event(vm_name, vmid, 'vm_deleted', 'vmid', str(vmid), '', notified=True)

    def detect_config_drift(self, vm_id: int, vm_name: str, vm_config: Dict[str, Any],
                            current_tags: List[str], network_interfaces: List[Dict] = None,
                            current_node: str = None) -> List[Dict]:
        if not self.enhanced_mode or not self.state_db:
            return []
        drifts = []
        last_config = self.state_db.get_last_vm_config(vm_id, self.cluster_name)
        if not last_config:
            return drifts
        current_memory = int(vm_config.get('memory', 0))
        current_vcpus = int(vm_config.get('vcpus',
                           int(vm_config.get('cores', 1)) * int(vm_config.get('sockets', 1))))
        old_memory = last_config.get('memory', 0)
        old_vcpus = last_config.get('vcpus', 0)
        if current_memory != old_memory:
            drifts.append({'field': 'memory', 'old': old_memory, 'new': current_memory, 'unit': 'MB'})
        if current_vcpus != old_vcpus:
            drifts.append({'field': 'vcpus', 'old': old_vcpus, 'new': current_vcpus, 'unit': 'core'})

        # VM 更名偵測
        old_name = last_config.get('vm_name')
        if old_name and old_name != vm_name:
            print(f"✏️  VM 更名偵測: {old_name} → {vm_name} (ID: {vm_id})")
            self.stats['config_drifts_detected'] += 1
            rename_msg = (
                f"✏️ <b>VM 更名偵測</b>\n\n"
                f"🖥️ 原名稱: <b>{old_name}</b> → <b>{vm_name}</b>\n"
                f"🔢 ID: {vm_id}\n"
                f"🔀 叢集: {self.cluster_name}\n"
                f"📅 時間: {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.send_telegram_notification(rename_msg)
            self._write_drift_event(vm_name, vm_id, 'vm_renamed', 'name', old_name, vm_name, notified=True)

        # VM 遷移偵測（節點變更）
        old_node = last_config.get('node')
        if old_node and current_node and old_node != current_node:
            print(f"🚚 VM {vm_name} 遷移偵測: {old_node} → {current_node}")
            self.stats['config_drifts_detected'] += 1
            migration_msg = (
                f"🚚 <b>VM 遷移偵測</b>\n\n"
                f"🖥️ 名稱: <b>{vm_name}</b> (ID: {vm_id})\n"
                f"🔀 叢集: {self.cluster_name}\n"
                f"📅 時間: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"📤 來源節點: <code>{old_node}</code>\n"
                f"📥 目標節點: <code>{current_node}</code>"
            )
            self.send_telegram_notification(migration_msg)
            self._write_drift_event(vm_name, vm_id, 'migration', 'node', old_node, current_node, notified=True)

        # 磁碟配置變更偵測
        current_disks = self._parse_disk_summary(vm_config)
        old_disks = last_config.get('disk_summary') or {}
        if old_disks:  # 只在有先前記錄時比對
            added_disks = {k: v for k, v in current_disks.items() if k not in old_disks}
            removed_disks = {k: v for k, v in old_disks.items() if k not in current_disks}
            resized_disks = {
                k: (old_disks[k], current_disks[k])
                for k in current_disks
                if k in old_disks and old_disks[k] != current_disks[k]
            }
            if added_disks or removed_disks or resized_disks:
                self.stats['config_drifts_detected'] += 1
                detail = ""
                for k, v in added_disks.items():
                    detail += f"➕ 新增磁碟: <code>{k}</code> ({v})\n"
                for k, v in removed_disks.items():
                    detail += f"➖ 移除磁碟: <code>{k}</code> (原 {v})\n"
                for k, (old_v, new_v) in resized_disks.items():
                    detail += f"🔄 磁碟調整: <code>{k}</code>  {old_v} → {new_v}\n"
                print(f"💾 VM {vm_name} 磁碟配置變更")
                disk_msg = (
                    f"💾 <b>VM 磁碟配置變更</b>\n\n"
                    f"🖥️ 名稱: <b>{vm_name}</b> (ID: {vm_id})\n"
                    f"🔀 叢集: {self.cluster_name}\n"
                    f"📅 時間: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"{detail}"
                )
                self.send_telegram_notification(disk_msg)
                for k, v in added_disks.items():
                    self._write_drift_event(vm_name, vm_id, 'disk_change', k, '', v, notified=True)
                for k, v in removed_disks.items():
                    self._write_drift_event(vm_name, vm_id, 'disk_change', k, v, '', notified=True)
                for k, (old_v, new_v) in resized_disks.items():
                    self._write_drift_event(vm_name, vm_id, 'disk_change', k, old_v, new_v, notified=True)

        # VM 描述變更偵測
        current_desc = (vm_config.get('description') or '').strip()[:500]
        old_desc = (last_config.get('description') or '').strip()
        if old_desc and old_desc != current_desc:
            self.stats['config_drifts_detected'] += 1
            print(f"📝 VM {vm_name} 描述變更")
            desc_preview = current_desc[:100] + ('…' if len(current_desc) > 100 else '')
            desc_msg = (
                f"📝 <b>VM 描述變更</b>\n\n"
                f"🖥️ 名稱: <b>{vm_name}</b> (ID: {vm_id})\n"
                f"🔀 叢集: {self.cluster_name}\n"
                f"📅 時間: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"📄 新描述: <code>{desc_preview}</code>"
            )
            self.send_telegram_notification(desc_msg)
            self._write_drift_event(vm_name, vm_id, 'description_change', 'description',
                                    old_desc[:200], current_desc[:200], notified=True)

        if drifts:
            self.stats['config_drifts_detected'] += len(drifts)
            print(f"🔄 VM {vm_name} 硬體配置漂移: {len(drifts)} 處變更")
            detail_lines = ""
            for drift in drifts:
                detail_lines += f"• {drift['field']}: {drift['old']} → {drift['new']} {drift.get('unit', '')}\n"
            hw_msg = (
                f"🔄 <b>VM 硬體配置變更</b>\n\n"
                f"🖥️ 名稱: <b>{vm_name}</b> (ID: {vm_id})\n"
                f"🔀 叢集: {self.cluster_name}\n"
                f"📅 時間: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"{detail_lines}\n請確認是否為預期變更。"
            )
            self.send_telegram_notification(hw_msg)
            for drift in drifts:
                self._write_drift_event(
                    vm_name, vm_id, 'hardware', drift['field'],
                    f"{drift['old']} {drift.get('unit', '')}".strip(),
                    f"{drift['new']} {drift.get('unit', '')}".strip(),
                    notified=True,
                )
        return drifts

    def should_sync_vm(self, vm_id: int, vm_config: Dict[str, Any], tags: List[str],
                       network_interfaces: List[Dict] = None) -> bool:
        if not self.sync_config.get('incremental', True):
            return True
        if self.sync_config.get('force_full_sync', False):
            return True
        current_hash = compute_config_hash(vm_config, tags, network_interfaces)
        if not self.state_db:
            return True
        last_config = self.state_db.get_last_vm_config(vm_id, self.cluster_name)
        if not last_config:
            return True
        if current_hash != last_config.get('config_hash'):
            return True
        return False

    def detect_tag_changes(self, vm_id: int, vm_name: str, current_tags: List[str]) -> List[Dict]:
        if not self.enhanced_mode or not self.state_db:
            return []
        changes = []
        last_config = self.state_db.get_last_vm_config(vm_id, self.cluster_name)
        if not last_config:
            return changes
        old_tags = set(last_config.get('tags', []))
        new_tags = set(current_tags)
        added = new_tags - old_tags
        removed = old_tags - new_tags
        for tag in added:
            changes.append({'type': 'added', 'tag': tag})
            self.stats['tag_changes'] += 1
            print(f"🏷️  VM {vm_name} 新增標籤: {tag}")
            self._write_drift_event(vm_name, vm_id, 'tag_change', 'tags', '', tag, notified=False)
        for tag in removed:
            changes.append({'type': 'removed', 'tag': tag})
            self.stats['tag_changes'] += 1
            print(f"🏷️  VM {vm_name} 移除標籤: {tag}")
            self._write_drift_event(vm_name, vm_id, 'tag_change', 'tags', tag, '', notified=False)
        if changes:
            added_list = [c['tag'] for c in changes if c['type'] == 'added']
            removed_list = [c['tag'] for c in changes if c['type'] == 'removed']
            detail = ""
            if added_list:
                detail += f"➕ 新增標籤: <code>{', '.join(added_list)}</code>\n"
            if removed_list:
                detail += f"➖ 移除標籤: <code>{', '.join(removed_list)}</code>\n"
            tag_msg = (
                f"🏷️ <b>VM 標籤變更</b>\n\n"
                f"🖥️ 名稱: <b>{vm_name}</b> (ID: {vm_id})\n"
                f"🔀 叢集: {self.cluster_name}\n"
                f"📅 時間: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"{detail}\n請確認是否為預期變更。"
            )
            self.send_telegram_notification(tag_msg)
        return changes

    def detect_ip_change(self, vm_id: int, vm_name: str, current_ip: str):
        """Compare current primary IP to state_db snapshot; notify and record if changed."""
        if not self.enhanced_mode or not self.state_db:
            return
        last_config = self.state_db.get_last_vm_config(vm_id, self.cluster_name)
        if not last_config:
            return
        old_ip = last_config.get('primary_ip') or ''
        if not old_ip or old_ip == current_ip:
            return
        print(f"🌐 VM {vm_name} IP 變更: {old_ip} → {current_ip}")
        self.stats['config_drifts_detected'] += 1
        ip_msg = (
            f"🌐 <b>VM IP 位址變更</b>\n\n"
            f"🖥️ 名稱: <b>{vm_name}</b> (ID: {vm_id})\n"
            f"🔀 叢集: {self.cluster_name}\n"
            f"📅 時間: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"🔄 舊 IP: <code>{old_ip}</code>\n"
            f"🔄 新 IP: <code>{current_ip}</code>\n\n"
            f"請確認是否為預期變更。"
        )
        self.send_telegram_notification(ip_msg)
        self._write_drift_event(vm_name, vm_id, 'ip_change', 'primary_ip', old_ip, current_ip, notified=True)

    # ---------- 虛擬機處理主邏輯 ----------
    def process_virtual_machine(self, vm_data: Dict, device, cluster: Dict, force: bool = False) -> bool:
        vm_id = str(vm_data['vmid'])
        original_vm_name = vm_data['name']
        vm_type = vm_data.get('type', 'qemu')
        node_name = vm_data['node']
        vm_name = self.get_unique_vm_name(original_vm_name, vm_id, cluster['id'])
        print(f"處理虛擬機: {original_vm_name} (ID: {vm_id}, 類型: {vm_type.upper()}) -> {vm_name}")
        try:
            if 'config' in vm_data:
                vm_config = vm_data['config']
            else:
                if vm_type == 'qemu':
                    vm_config = self.pve_api.nodes(node_name).qemu(vm_data['vmid']).config.get()
                else:
                    vm_config = self.pve_api.nodes(node_name).lxc(vm_data['vmid']).config.get()
        except Exception as e:
            print(f"  獲取 VM 配置失敗: {e}")
            return False
        is_template = vm_data.get('is_template', False) or vm_config.get('template', 0) == 1
        boot_choice = 'on' if vm_config.get('onboot', 0) == 1 else 'off'
        tag_ids = []
        tag_names = []
        if 'tags' in vm_config and vm_config['tags']:
            tag_list = vm_config['tags'].split(';')
            for tag_name in tag_list:
                tag_name = tag_name.strip()
                if tag_name:
                    tag_names.append(tag_name)
                    if tag_name in self.nb_cache['tags']:
                        tag_ids.append(self.nb_cache['tags'][tag_name].id)
                    else:
                        try:
                            slug = tag_name.lower().replace(' ', '-').replace('/', '-')
                            tag = self.nb_api.extras.tags.create(
                                name=tag_name, slug=slug[:50], description=f"Proxmox tag: {tag_name}"
                            )
                            self.nb_cache['tags'][tag_name] = tag
                            tag_ids.append(tag.id)
                        except Exception as e:
                            print(f"  建立標籤失敗 {tag_name}: {e}")
        if self.enhanced_mode:
            self.detect_new_vm(int(vm_id), original_vm_name, node_name)
        if self.enhanced_mode and tag_names:
            self.detect_tag_changes(int(vm_id), original_vm_name, tag_names)
        vm_status = vm_data.get('status', '')
        if tag_names and vm_status in ('running', 'stopped'):
            first_tag = tag_names[0].lower()
            node_name = vm_data.get('node', 'unknown')
            if first_tag == '0n' and vm_status == 'stopped':
                message = f"""
⚠️ <b>虛擬機意外關機</b>

🖥️ 名稱: <b>{original_vm_name}</b> (ID: {vm_id})
📌 節點: {node_name}
🏷️ 期望狀態: <code>ON</code>
🔴 目前狀態: <b>stopped</b>

❌ 虛擬機應處於開機狀態，請立即檢查。
"""
                self.send_telegram_notification(message)
            elif first_tag == '0ff' and vm_status == 'running':
                message = f"""
⚠️ <b>虛擬機意外開機</b>

🖥️ 名稱: <b>{original_vm_name}</b> (ID: {vm_id})
📌 節點: {node_name}
🏷️ 期望狀態: <code>OFF</code>
🟢 目前狀態: <b>running</b>

⚠️ 虛擬機應處於關機狀態，請確認開機原因。
"""
                self.send_telegram_notification(message)
        role_id = None
        vm_pool = self.get_vm_pool(vm_data['vmid'], vm_type)
        if vm_pool:
            role_id = self.get_or_create_vm_role(vm_pool)
            print(f"  使用 PVE Pool 作為角色: {vm_pool}")
        else:
            role_id = self.get_or_create_vm_role('Virtual Machine' if vm_type == 'qemu' else 'Container')
        agent_interfaces = {}
        mac_to_interface = {}
        if vm_type == 'qemu' and not is_template and vm_data.get('status') == 'running':
            agent_interfaces, mac_to_interface = self.get_vm_agent_network_info(node_name, vm_data['vmid'], vm_type)
        platform_id = None
        ostype = vm_config.get('ostype')
        if ostype:
            platform_key = ostype.lower()
            if platform_key in self.nb_cache['platforms']:
                platform_id = self.nb_cache['platforms'][platform_key].id
            else:
                try:
                    platform = self.nb_api.dcim.platforms.create(
                        name=ostype, slug=ostype.lower().replace(' ', '-').replace('/', '-')[:50],
                        description=f"Proxmox OS Type: {ostype}"
                    )
                    self.nb_cache['platforms'][platform_key] = platform
                    platform_id = platform.id
                except Exception as e:
                    print(f"  建立平台失敗 {ostype}: {e}")
        if 'vcpus' in vm_config:
            vcpus = int(vm_config['vcpus'])
        else:
            cores = int(vm_config.get('cores', 1))
            sockets = int(vm_config.get('sockets', 1))
            vcpus = cores * sockets
        if is_template:
            status = 'staged'
        elif vm_data.get('status') == 'running':
            status = 'active'
        else:
            status = 'offline'
        qemu_agent_enabled = False
        if vm_type == 'qemu' and 'agent' in vm_config:
            qemu_agent_enabled = self.check_qemu_agent(vm_config)
        network_interfaces = []
        for key, value in vm_config.items():
            if key.startswith('net'):
                net_cfg = self.parse_network_config(value)
                network_interfaces.append({
                    'name': key,
                    'mac_address': net_cfg.get('virtio') or net_cfg.get('e1000') or net_cfg.get('vmxnet3') or net_cfg.get('rtl8139') or '',
                    'bridge': net_cfg.get('bridge', ''),
                    'gateway': ''
                })
        if self.enhanced_mode:
            self.detect_config_drift(int(vm_id), original_vm_name, vm_config, tag_names,
                                     network_interfaces, current_node=node_name)
            if not force and not self.should_sync_vm(int(vm_id), vm_config, tag_names, network_interfaces):
                cached_vm = self.nb_cache['virtual_machines_by_serial'].get(f"{vm_id}::{cluster['id']}")
                if cached_vm is None:
                    # VM 在 NetBox 中不存在（例如隨節點被連帶刪除），
                    # 但 state_db 仍有舊 hash 導致增量跳過。強制往下完整同步。
                    print(f"  ⚠️  VM {original_vm_name} 不在 NetBox 中，忽略增量記錄強制建立")
                else:
                    # VM 存在；確保 device 關聯指向正確節點
                    current_device_id = getattr(getattr(cached_vm, 'device', None), 'id', None)
                    current_cluster_id = getattr(getattr(cached_vm, 'cluster', None), 'id', None)
                    fix = {}
                    if current_device_id != device.id:
                        fix['device'] = device.id
                    if current_cluster_id != cluster['id']:
                        fix['cluster'] = cluster['id']
                    if fix:
                        try:
                            cached_vm.update(fix)
                            if 'cluster' in fix:
                                print(f"  ✓ VM {original_vm_name} 叢集關聯已修正: → {cluster['name']}")
                            if 'device' in fix:
                                print(f"  ✓ VM {original_vm_name} 設備關聯已修正: → {device.name}")
                        except Exception as e:
                            print(f"  ✗ 更新 VM {original_vm_name} 關聯失敗: {e}")
                    print(f"  ℹ️  VM {original_vm_name} 無配置變更，跳過同步")
                    if self.state_db:
                        try:
                            config_hash = compute_config_hash(vm_config, tag_names, network_interfaces)
                            memory = int(vm_config.get('memory', 0))
                            vcpus_save = int(vm_config.get('vcpus', vcpus))
                            cur_ip = getattr(getattr(cached_vm, 'primary_ip4', None), 'address', None) or ''
                            self.state_db.save_vm_config_snapshot(
                                vm_id=int(vm_id), cluster_name=self.cluster_name, config_hash=config_hash,
                                memory=memory, vcpus=vcpus_save, tags=tag_names,
                                node=node_name, primary_ip=cur_ip, vm_name=original_vm_name,
                                description=(vm_config.get('description') or '').strip()[:500],
                                disk_summary=json.dumps(self._parse_disk_summary(vm_config)),
                            )
                        except Exception as _snap_err:
                            print(f"  ⚠ 跳過快照更新失敗: {_snap_err}")
                    return True
                # cached_vm is None → 繼續往下完整建立此 VM
        custom_fields = {}
        if self.custom_fields_created:
            # 清理衝突的 vm_id
            conflicting_vms = []
            for nb_vm in self.nb_cache['virtual_machines'].values():
                if hasattr(nb_vm, 'custom_fields') and nb_vm.custom_fields:
                    existing_vm_id = nb_vm.custom_fields.get('vm_id')
                    if existing_vm_id == vm_data['vmid']:
                        is_same_vm = False
                        if nb_vm.serial and str(nb_vm.serial) == vm_id:
                            is_same_vm = True
                        elif nb_vm.name == vm_name or nb_vm.name == original_vm_name:
                            is_same_vm = True
                        if not is_same_vm:
                            conflicting_vms.append(nb_vm)
            if conflicting_vms:
                print(f"  警告: 發現 {len(conflicting_vms)} 個其他虛擬機使用了相同的 vm_id ({vm_id}):")
                for conflict_vm in conflicting_vms:
                    print(f"    - {conflict_vm.name} (ID: {conflict_vm.id})")
                for conflict_vm in conflicting_vms:
                    try:
                        current_custom_fields = conflict_vm.custom_fields.copy() if conflict_vm.custom_fields else {}
                        if 'vm_id' in current_custom_fields:
                            del current_custom_fields['vm_id']
                            conflict_vm.custom_fields = current_custom_fields
                            conflict_vm.save()
                            print(f"    已從虛擬機 {conflict_vm.name} 中清除 vm_id")
                    except Exception as e:
                        print(f"    清除虛擬機 {conflict_vm.name} 的 vm_id 失敗: {e}")
            custom_fields = {
                'vm_id': vm_data['vmid'],
                'qemu_agent': qemu_agent_enabled,
                'ha': False,
                'replicated': False,
                'machine_type': vm_config.get('machine', '')
            }
        try:
            existing_vm = None
            serial_key = f"{vm_id}::{cluster['id']}"
            if serial_key in self.nb_cache['virtual_machines_by_serial']:
                existing_vm = self.nb_cache['virtual_machines_by_serial'][serial_key]
            if existing_vm is None:
                key = f"{vm_name.lower()}::{cluster['id']}"
                if key in self.nb_cache['virtual_machines_by_name']:
                    existing_vm = self.nb_cache['virtual_machines_by_name'][key]
            if existing_vm:
                print(f"  更新現有虛擬機: {existing_vm.name}")
                update_data = {
                    'name': vm_name, 'cluster': cluster['id'], 'device': device.id, 'role': role_id,
                    'vcpus': vcpus, 'memory': int(vm_config.get('memory', 0)), 'status': status,
                    'description': (vm_config.get('description') or '')[:200], 'platform': platform_id,
                    'start_on_boot': boot_choice
                }
                if tag_ids:
                    update_data['tags'] = tag_ids
                if custom_fields:
                    update_data['custom_fields'] = custom_fields
                existing_vm.update(update_data)
                vm_obj = existing_vm
                if existing_vm.name != vm_name:
                    old_key = f"{existing_vm.name.lower()}::{cluster['id']}"
                    if old_key in self.nb_cache['virtual_machines_by_name']:
                        del self.nb_cache['virtual_machines_by_name'][old_key]
                    new_key = f"{vm_name.lower()}::{cluster['id']}"
                    self.nb_cache['virtual_machines_by_name'][new_key] = existing_vm
            else:
                vm_data_dict = {
                    'serial': vm_id, 'name': vm_name, 'cluster': cluster['id'], 'device': device.id,
                    'role': role_id, 'vcpus': vcpus, 'memory': int(vm_config.get('memory', 0)),
                    'status': status, 'description': (vm_config.get('description') or '')[:200],
                    'platform': platform_id, 'start_on_boot': boot_choice
                }
                if tag_ids:
                    vm_data_dict['tags'] = tag_ids
                if custom_fields:
                    vm_data_dict['custom_fields'] = custom_fields
                vm_obj = self.nb_api.virtualization.virtual_machines.create(**vm_data_dict)
                self.nb_cache['virtual_machines'][vm_obj.id] = vm_obj
                self.nb_cache['virtual_machines_by_serial'][f"{vm_id}::{cluster['id']}"] = vm_obj
                key = f"{vm_name.lower()}::{cluster['id']}"
                self.nb_cache['virtual_machines_by_name'][key] = vm_obj
                print(f"  建立虛擬機: {vm_name}")
            # 處理介面（傳入device）
            interface_count, primary_ip, interfaces_data = self.process_vm_interfaces(
                vm_obj, vm_config, agent_interfaces, mac_to_interface, device
            )
            disk_count, disk_size = self.process_vm_disks(vm_obj, vm_config)
            primary_ip_str = ''
            if primary_ip:
                try:
                    vm_obj.primary_ip4 = primary_ip.id
                    vm_obj.save()
                    primary_ip_str = getattr(primary_ip, 'address', '') or ''
                except Exception as e:
                    print(f"  設定 VM 主 IP 失敗: {e}")
            if self.enhanced_mode and primary_ip_str:
                self.detect_ip_change(int(vm_id), original_vm_name, primary_ip_str)
            print(f"  標籤: {len(tag_ids)}個, 介面: {interface_count}個, 磁碟: {disk_count}個, 大小: {disk_size}MB")
            if self.enhanced_mode and self.state_db:
                config_hash = compute_config_hash(vm_config, tag_names, network_interfaces)
                memory = int(vm_config.get('memory', 0))
                vcpus_save = int(vm_config.get('vcpus', vcpus))
                self.state_db.save_vm_config_snapshot(
                    vm_id=int(vm_id), cluster_name=self.cluster_name, config_hash=config_hash,
                    memory=memory, vcpus=vcpus_save, tags=tag_names,
                    node=node_name, primary_ip=primary_ip_str, vm_name=original_vm_name,
                    description=(vm_config.get('description') or '').strip()[:500],
                    disk_summary=json.dumps(self._parse_disk_summary(vm_config)),
                )
            return True
        except Exception as e:
            error_msg = str(e)
            print(f"  處理虛擬機失敗: {error_msg}")
            # 即使 NetBox 同步失敗，仍需更新 snapshot 的非 hash 欄位（vm_name, node,
            # disk_summary, description, tags, memory, vcpus），並保留舊 config_hash，
            # 使下一輪不重複發送漂移通知，同時 should_sync_vm() 仍會返回 True 繼續重試。
            if self.enhanced_mode and self.state_db:
                try:
                    _lc = self.state_db.get_last_vm_config(int(vm_id), self.cluster_name)
                    if _lc:
                        _ip = locals().get('primary_ip_str') or _lc.get('primary_ip') or ''
                        self.state_db.save_vm_config_snapshot(
                            vm_id=int(vm_id),
                            cluster_name=self.cluster_name,
                            config_hash=_lc.get('config_hash'),
                            memory=int(vm_config.get('memory', 0)),
                            vcpus=int(vm_config.get('vcpus', vcpus)),
                            tags=tag_names,
                            node=node_name,
                            primary_ip=_ip,
                            vm_name=original_vm_name,
                            description=(vm_config.get('description') or '').strip()[:500],
                            disk_summary=json.dumps(self._parse_disk_summary(vm_config)),
                        )
                except Exception:
                    pass
            return False

    # ---------- 批量同步VM ----------
    def sync_pve_virtual_machines(self, devices: Dict[str, Any], cluster: Dict) -> Tuple[bool, int, int]:
        print("\n開始同步虛擬機...")
        success_count = 0
        total_count = 0
        # 載入先前已知 vmid，用於偵測新增/刪除
        if self.enhanced_mode and self.state_db:
            self._known_vmids = self.state_db.get_known_vmids(self.cluster_name)
        seen_vmids: set = set()
        for node_name, vms in self.pve_cache['vms_by_node'].items():
            print(f"\n處理節點 {node_name} 的虛擬機:")
            print(f"  發現 {len(vms)} 個虛擬機")
            device = devices.get(node_name.lower())
            if not device:
                print(f"  ✗ 找不到對應的設備: {node_name}")
                continue
            node_is_new = node_name.lower() in self._newly_created_nodes
            if node_is_new:
                print(f"  ℹ️  節點 {node_name} 為新建，強制全量同步所有 VM")
            for vm in vms:
                total_count += 1
                vm['node'] = node_name
                seen_vmids.add(int(vm['vmid']))
                if self.process_virtual_machine(vm, device, cluster, force=node_is_new):
                    success_count += 1
        # 偵測本次同步消失的 VM（已從 PVE 刪除）
        self.detect_deleted_vms(seen_vmids)
        print(f"\n虛擬機同步完成: {success_count}/{total_count} 個虛擬機")
        return success_count > 0, success_count, total_count

    # ---------- 主同步 ----------
    def sync(self):
        print("開始優化的 PVE 到 NetBox 同步")
        print("=" * 50)
        if self.enhanced_mode and self.state_db:
            self.sync_log_id = self.state_db.start_sync_log(self.cluster_name)
        sync_mode = "增量" if self.sync_config.get('incremental', True) else "全量"
        start_message = f"""
🔄 <b>PVE-NetBox 同步開始</b>

📅 時間: {time.strftime("%Y-%m-%d %H:%M:%S")}
🚀 集群: {self.cluster_name}
⏳ 模式: {sync_mode}
"""
        self.send_telegram_notification(start_message)
        start_time = time.time()
        self.connect_pve()
        if not self.connect_netbox():
            return
        self.load_all_netbox_objects()
        if not self.check_required_custom_fields():
            print("\n同步中止。")
            return
        self.load_pve_data()
        self.show_summary()
        nodes_success, devices, cluster = self.sync_pve_nodes_to_netbox()
        if nodes_success and devices and cluster:
            print("\n" + "=" * 50)
            print("✓ 節點同步成功")
            vms_success, success_count, total_count = self.sync_pve_virtual_machines(devices, cluster)
            elapsed = time.time() - start_time
            self.stats['elapsed_time'] = elapsed
            self.stats['total_vms'] = total_count
            self.stats['success_vms'] = success_count
            if self.enhanced_mode and self.state_db and hasattr(self, 'sync_log_id'):
                status = 'success' if vms_success else 'partial'
                self.state_db.update_sync_log(self.sync_log_id, success_count, total_count, status)
            self.send_enhanced_summary()
            if vms_success:
                print("✓ 虛擬機同步成功")
            else:
                print("⚠ 虛擬機同步部分失敗")
        else:
            elapsed = time.time() - start_time
            print(f"\n同步失敗，總耗時: {elapsed:.2f} 秒")
            print("✗ 節點同步失敗")
            failure_message = f"""
❌ <b>PVE-NetBox 同步失敗</b>

📅 時間: {time.strftime("%Y-%m-%d %H:%M:%S")}
⏱️ 耗時: {elapsed:.2f} 秒
❌ 原因: 節點同步失敗
"""
            self.send_telegram_notification(failure_message)

    def show_summary(self):
        print("\n" + "="*50)
        print("同步摘要")
        print("="*50)
        print(f"PVE 節點: {len(self.pve_cache['nodes'])} 個")
        print(f"PVE Pools: {len(self.pve_cache['pools'])} 個")
        total_vms = sum(len(vms) for vms in self.pve_cache['vms_by_node'].values())
        qemu_count = 0
        lxc_count = 0
        for node_name, vms in self.pve_cache['vms_by_node'].items():
            for vm in vms:
                if vm.get('type') == 'qemu':
                    qemu_count += 1
                elif vm.get('type') == 'lxc':
                    lxc_count += 1
        print(f"PVE 虛擬機: {total_vms} 個 (QEMU: {qemu_count}, LXC: {lxc_count})")
        print(f"\nNetBox 快取統計:")
        print(f"  設備: {len(self.nb_cache['devices'])} 個")
        print(f"  虛擬機: {len(self.nb_cache['virtual_machines'])} 個")
        print(f"  標籤: {len(self.nb_cache['tags'])} 個")
        print(f"  角色: {len(self.nb_cache['roles'])} 個")
        print(f"  IP位址: {len(self.nb_cache['ip_addresses'])} 個")
        print("="*50)


def main():
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    required_env_vars = [
        'PVE_API_HOST', 'PVE_API_USER', 'PVE_API_TOKEN', 'PVE_API_SECRET',
        'NB_API_URL', 'NB_API_TOKEN', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID',
    ]
    missing_vars = [var for var in required_env_vars if var not in os.environ]
    if missing_vars:
        print(f"✗ 缺少必要環境變數: {', '.join(missing_vars)}")
        print("請設定以下環境變數:")
        for var in required_env_vars:
            print(f"  export {var}=value")
        sys.exit(1)
    sync = OptimizedPVEToNetBoxSync()
    sync.sync()


if __name__ == '__main__':
    main()
