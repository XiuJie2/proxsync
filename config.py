"""
配置管理模块 (Config Manager)
支持 YAML 配置文件、环境变量覆盖、热重载
"""

import os
import yaml
import threading
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time


class ConfigChangeHandler(FileSystemEventHandler):
    """配置文件变更处理器"""

    def __init__(self, config_manager):
        self.config_manager = config_manager

    def on_modified(self, event):
        if not event.is_directory and event.src_path == self.config_manager.config_file:
            print(f"🔄 配置文件已变更: {event.src_path}")
            self.config_manager.reload()


class ConfigManager:
    """配置管理器 - 支持热重载"""

    def __init__(self, config_file: str = "/etc/pve-sync/config.yaml"):
        """
        初始化配置管理器

        Args:
            config_file: YAML 配置文件路径
        """
        self.config_file = Path(config_file)
        self.config: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._observer = None
        self._enabled = True  # 控制热重载是否启用

        # 首次加载
        self._load_config()
        self._start_watcher()

    def _load_config(self):
        """加载配置文件（线程安全）"""
        with self._lock:
            if not self.config_file.exists():
                # 如果配置文件不存在，使用默认值 + 环境变量
                self.config = self._build_default_config()
                return

            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f) or {}

                # 环境变量覆盖机制
                self.config = self._apply_env_overrides(yaml_config)
                print(f"✓ 配置已加载: {self.config_file}")

            except Exception as e:
                print(f"✗ 配置加载失败: {e}")
                # 保留旧配置（如果存在）
                if not self.config:
                    self.config = self._build_default_config()

    def _build_default_config(self) -> Dict[str, Any]:
        """从环境变量构建默认配置"""
        return {
            'clusters': [
                {
                    'name': 'default',
                    'pve': {
                        'host': os.getenv('PVE_API_HOST', ''),
                        'user': os.getenv('PVE_API_USER', ''),
                        'token': os.getenv('PVE_API_TOKEN', ''),
                        'secret': os.getenv('PVE_API_SECRET', ''),
                        'verify_ssl': os.getenv('PVE_API_VERIFY_SSL', 'false').lower() == 'true'
                    },
                    'netbox': {
                        'url': os.getenv('NB_API_URL', ''),
                        'token': os.getenv('NB_API_TOKEN', '')
                    },
                    'settings': {
                        'cluster_name': os.getenv('NB_CLUSTER_NAME', 'Proxmox Cluster'),
                        'site_name': os.getenv('NB_SITE_NAME', 'Main Datacenter'),
                        'cluster_type': os.getenv('NB_CLUSTER_TYPE', 'Proxmox')
                    }
                }
            ],
            'telegram': {
                'enabled': bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID')),
                'bot_token': os.getenv('TELEGRAM_BOT_TOKEN', ''),
                'chat_id': os.getenv('TELEGRAM_CHAT_ID', '')
            },
            'monitoring': {
                'node_offline_alert': True,
                'config_drift_alert': True,
                'resource_alert': {
                    'enabled': True,
                    'memory_threshold': 85,  # %
                    'cpu_threshold': 90,     # %
                    'disk_threshold': 10,    # % free space
                    'check_interval_hours': 6
                },
                'tag_change_alert': True
            },
            'sync': {
                'incremental': True,
                'force_full_sync': False,
                'batch_size': 50,  # 批量处理 VM 的数量
                'node_batch_size': 10,  # 预加载每个节点的 VM 配置数量
                'default_node_role': 'PVE',
                'default_node_type': 'Standard Server'
            },
            'webhook': {
                'enabled': False,
                'host': '0.0.0.0',
                'port': 8080,
                'secret': os.getenv('WEBHOOK_SECRET', ''),  # 签名验证密钥
                'rate_limit': 10  # 每秒最多处理的事件数
            },
            'plugins': {
                'enabled': False,
                'netbox_integration': True,  # 是否作为 NetBox 插件运行
                'plugin_slug': 'pve-netbox-sync'
            },
            'state_db': {
                'path': '/var/lib/pve-sync/state.db',
                'cleanup_days': 90
            },
            'logging': {
                'level': 'INFO',
                'directory': '/var/log/pve-sync',
                'max_files': 30
            }
        }

    def _apply_env_overrides(self, yaml_config: Dict[str, Any]) -> Dict[str, Any]:
        """应用环境变量覆盖（环境变量优先级最高）"""
        # 环境变量映射表
        env_mappings = {
            'PVE_API_HOST': ('clusters', 0, 'pve', 'host'),
            'PVE_API_USER': ('clusters', 0, 'pve', 'user'),
            'PVE_API_TOKEN': ('clusters', 0, 'pve', 'token'),
            'PVE_API_SECRET': ('clusters', 0, 'pve', 'secret'),
            'PVE_API_VERIFY_SSL': ('clusters', 0, 'pve', 'verify_ssl'),
            'NB_API_URL': ('clusters', 0, 'netbox', 'url'),
            'NB_API_TOKEN': ('clusters', 0, 'netbox', 'token'),
            'NB_CLUSTER_NAME': ('clusters', 0, 'settings', 'cluster_name'),
            'NB_SITE_NAME': ('clusters', 0, 'settings', 'site_name'),
            'TELEGRAM_BOT_TOKEN': ('telegram', 'bot_token'),
            'TELEGRAM_CHAT_ID': ('telegram', 'chat_id'),
            'WEBHOOK_SECRET': ('webhook', 'secret'),
        }

        merged = yaml_config.copy()

        for env_key, path in env_mappings.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                # 遍历路径，逐层创建/设置
                current = merged
                for i, key in enumerate(path[:-1]):
                    if isinstance(key, int):  # 数组索引
                        if len(current) <= key:
                            current.append({})
                        current = current[key]
                    else:
                        if key not in current:
                            current[key] = {} if i < len(path) - 2 else None
                        current = current[key]

                # 设置值
                final_key = path[-1]
                if isinstance(final_key, int):
                    if len(current) <= final_key:
                        current.append(env_value)
                    else:
                        current[final_key] = env_value
                else:
                    # 类型转换
                    if final_key == 'verify_ssl':
                        current[final_key] = env_value.lower() == 'true'
                    else:
                        current[final_key] = env_value

        return merged

    def _start_watcher(self):
        """启动文件监视器"""
        if not self._enabled:
            return

        try:
            self._observer = Observer()
            handler = ConfigChangeHandler(self)
            self._observer.schedule(handler, self.config_file.parent, recursive=False)
            self._observer.start()
            print(f"🔄 配置热重载已启用，监控: {self.config_file}")
        except Exception as e:
            print(f"⚠ 配置热重载不可用 (watchdog 未安装?): {e}")
            self._observer = None

    def reload(self):
        """重新加载配置（由 watchdog 调用）"""
        old_config = self.config.copy()
        self._load_config()

        # 通知配置变更
        if old_config != self.config:
            print("✅ 配置已重新加载")
            # 这里可以触发回调，通知其他模块配置已变更

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        获取配置值（支持点分隔路径）

        Args:
            key_path: 配置路径，如 'telegram.enabled'、'clusters.0.pve.host'
            default: 默认值

        Returns:
            配置值或默认值
        """
        with self._lock:
            keys = key_path.split('.')
            value = self.config

            try:
                for key in keys:
                    # 处理数字索引
                    if key.isdigit():
                        key = int(key)
                    value = value[key]
                return value
            except (KeyError, IndexError, TypeError):
                return default

    def get_cluster_configs(self) -> List[Dict[str, Any]]:
        """获取所有集群配置"""
        return self.get('clusters', [])

    def get_telegram_config(self) -> Optional[Dict[str, Any]]:
        """获取 Telegram 配置"""
        telegram_config = self.get('telegram', {})
        if telegram_config.get('enabled'):
            return telegram_config
        return None

    def get_monitoring_config(self) -> Dict[str, Any]:
        """获取监控配置"""
        return self.get('monitoring', {})

    def get_sync_config(self) -> Dict[str, Any]:
        """获取同步配置"""
        return self.get('sync', {})

    def get_webhook_config(self) -> Optional[Dict[str, Any]]:
        """获取 Webhook 配置"""
        webhook_config = self.get('webhook', {})
        if webhook_config.get('enabled'):
            return webhook_config
        return None

    def get_state_db_config(self) -> Dict[str, Any]:
        """获取状态数据库配置"""
        return self.get('state_db', {})

    def stop(self):
        """停止配置监视器"""
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def __del__(self):
        """析构时停止监视器"""
        self.stop()


# 全局配置管理器单实例
_global_config: Optional[ConfigManager] = None


def init_config(config_file: str = None) -> ConfigManager:
    """初始化全局配置管理器"""
    global _global_config
    if _global_config is None:
        if config_file:
            _global_config = ConfigManager(config_file)
        else:
            # 默认路径查找
            paths = [
                '/etc/pve-sync/config.yaml',
                '/opt/pve-sync/config.yaml',
                'config.yaml',
                'config.example.yaml'
            ]
            for path in paths:
                if Path(path).exists():
                    _global_config = ConfigManager(path)
                    break
            else:
                _global_config = ConfigManager()  # 使用默认
    return _global_config


def get_config() -> ConfigManager:
    """获取全局配置管理器"""
    if _global_config is None:
        return init_config()
    return _global_config


if __name__ == "__main__":
    # 测试
    import sys

    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    else:
        config_file = "config.yaml"

    # 创建示例配置
    sample_config = ConfigManager(config_file)._build_default_config()

    print("=== 示例配置 ===")
    print(yaml.dump(sample_config, default_flow_style=False, allow_unicode=True))

    # 初始化并测试热重载
    cm = init_config(config_file)
    print("\n当前配置值:")
    print(f"  telegram.enabled: {cm.get('telegram.enabled')}")
    print(f"  monitoring.resource_alert.memory_threshold: {cm.get('monitoring.resource_alert.memory_threshold')}%")
    print(f"  clusters 数量: {len(cm.get_cluster_configs())}")
