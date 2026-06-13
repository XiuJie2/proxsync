"""NetBox PluginConfig for PVE-NetBox Sync (NetBox 4.x)."""

from netbox.plugins import PluginConfig

__version__ = "2.0.0"


class PveSyncPluginConfig(PluginConfig):
    """PVE Sync 插件配置 — NetBox 4.x compatible."""

    name = "pve_sync_plugin"
    verbose_name = "PVE-NetBox 同步"
    description = "将 Proxmox VE 环境同步到 NetBox，支持实时 Webhook 和手动触发"
    author = "PVE-NetBox Sync Maintainers"
    author_email = ""
    version = __version__
    base_url = "pve-sync"
    min_version = "4.5.0"
    max_version = "4.6.99"

    middleware = []
    queues = ["default"]

    required_settings = []
    default_settings = {
        "pve_api_host": "",
        "pve_api_user": "root@pam",
        "pve_api_token": "",
        "pve_api_secret": "",
        "pve_api_verify_ssl": False,
        "netbox_url": "",
        "netbox_token": "",
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "webhook_secret": "",
        "default_cluster_name": "default",
        "default_netbox_cluster": "Proxmox Cluster",
        "default_site": "Main Datacenter",
        "default_cluster_type": "Proxmox",
        "default_node_role": "PVE",
        "default_node_type": "Standard Server",
        "state_db_path": "/var/lib/netbox/pve-sync-state.db",
        "enable_backup_sync": True,
    }

    def ready(self):
        super().ready()
        import pve_sync_plugin.signals  # noqa: F401
