"""Plugin configuration for NetBox when running inside Docker.

This file is mounted as /etc/netbox/config/plugins.py and auto-loaded
by NetBox's configuration system.

All sensitive values should be passed via environment variables.
"""

import os

PLUGINS = ["pve_sync_plugin"]

PLUGINS_CONFIG = {
    "pve_sync_plugin": {
        "pve_api_host": os.environ.get("PVE_API_HOST", ""),
        "pve_api_user": os.environ.get("PVE_API_USER", "root@pam"),
        "pve_api_token": os.environ.get("PVE_API_TOKEN", ""),
        "pve_api_secret": os.environ.get("PVE_API_SECRET", ""),
        "pve_api_verify_ssl": os.environ.get("PVE_API_VERIFY_SSL", "false").lower() == "true",
        "netbox_url": os.environ.get("NB_API_URL", ""),
        "netbox_token": os.environ.get("NB_API_TOKEN", ""),
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "webhook_secret": os.environ.get("WEBHOOK_SECRET", ""),
        "default_cluster_name": os.environ.get("PVE_CLUSTER_NAME", "default"),
        "default_netbox_cluster": os.environ.get("PVE_NETBOX_CLUSTER", "Proxmox Cluster"),
        "default_site": os.environ.get("PVE_SITE", "Main Datacenter"),
        "default_cluster_type": os.environ.get("PVE_CLUSTER_TYPE", "Proxmox"),
        "default_node_role": os.environ.get("PVE_NODE_ROLE", "PVE"),
        "default_node_type": os.environ.get("PVE_NODE_TYPE", "Standard Server"),
        "state_db_path": os.environ.get("PVE_STATE_DB_PATH", "/var/lib/netbox/pve-sync-state.db"),
        "enable_backup_sync": os.environ.get("PVE_ENABLE_BACKUP_SYNC", "true").lower() == "true",
    },
}
