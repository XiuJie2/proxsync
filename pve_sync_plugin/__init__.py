"""NetBox plugin entrypoint for Proxmox Sync."""

from netbox.plugins import PluginConfig

__version__ = "2.1.0"


class PveSyncPluginConfig(PluginConfig):

    name = "pve_sync_plugin"
    verbose_name = "Proxmox Sync"
    description = "Synchronize Proxmox VE and Proxmox Backup Server inventory into NetBox."
    author = "Proxmox Sync Maintainers"
    author_email = ""
    version = __version__
    base_url = "pve-sync"
    min_version = "4.5.0"
    max_version = "4.6.99"

    middleware = []
    queues = ["default"]

    required_settings = []
    default_settings = {
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
        from pve_sync_plugin.signals import register_signals
        register_signals()


config = PveSyncPluginConfig
