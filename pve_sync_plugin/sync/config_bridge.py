"""Config bridge: translates plugin DB settings into the format expected by
the standalone sync engine (OptimizedPVEToNetBoxSync).

This module allows the sync engine to be driven either from:
  1. Plugin DB models (PvePluginSettings / PveClusterConfig)
  2. A YAML config file + env vars (standalone mode)
"""

import logging
import os
import tempfile

import yaml

logger = logging.getLogger(__name__)

# Environment variable keys managed by the config bridge.
# Used for setup and cleanup to avoid cross-worker pollution.
_ENV_KEYS = [
    "PVE_SYNC_CONFIG_FILE",
    "PVE_API_HOST",
    "PVE_API_USER",
    "PVE_API_TOKEN",
    "PVE_API_SECRET",
    "PVE_API_VERIFY_SSL",
    "NB_API_URL",
    "NB_API_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]


class ConfigValidationError(Exception):
    """Raised when required configuration values are missing."""


def validate_config(config_data):
    """Validate that required fields are present and non-empty.

    Raises:
        ConfigValidationError: if critical connection details are missing.
    """
    cluster = config_data.get("clusters", [{}])[0]
    pve = cluster.get("pve", {})
    netbox = cluster.get("netbox", {})

    missing = []
    if not pve.get("host"):
        missing.append("pve.host (PVE API host)")
    if not pve.get("token"):
        missing.append("pve.token (PVE API token)")
    if not pve.get("secret"):
        missing.append("pve.secret (PVE API secret)")
    if not netbox.get("url"):
        missing.append("netbox.url (NetBox API URL)")
    if not netbox.get("token"):
        missing.append("netbox.token (NetBox API token)")

    if missing:
        raise ConfigValidationError(
            f"Missing required config fields: {', '.join(missing)}"
        )


def build_runtime_config_from_db(cluster_name="default"):
    """Read plugin DB models and produce a config dict compatible with
    the standalone sync engine.

    Returns:
        dict: config in the same schema as config.yaml
    """
    from pve_sync_plugin.models import PveClusterConfig
    from pve_sync_plugin.utils import get_plugin_config

    cluster = PveClusterConfig.objects.filter(
        name=cluster_name, enabled=True
    ).first()

    if cluster:
        pve_host = cluster.pve_host
        pve_user = cluster.pve_user
        pve_token = cluster.pve_token
        pve_secret = cluster.pve_secret
        verify_ssl = cluster.pve_verify_ssl
        site_name = (
            cluster.netbox_site.name
            if cluster.netbox_site
            else get_plugin_config("default_site", "Main Datacenter")
        )
        cluster_type = (
            cluster.netbox_cluster_type.name
            if cluster.netbox_cluster_type
            else get_plugin_config("default_cluster_type", "Proxmox")
        )
        netbox_cluster = (
            cluster.netbox_cluster.name
            if cluster.netbox_cluster
            else get_plugin_config("default_netbox_cluster", "Proxmox Cluster")
        )
        logical_name = cluster.name
    else:
        raise ConfigValidationError(
            f"No enabled PVE cluster config found for cluster '{cluster_name}'. "
            "Please add a cluster in PVE Clusters → Add Cluster."
        )

    return {
        "clusters": [
            {
                "name": logical_name,
                "pve": {
                    "host": pve_host,
                    "user": pve_user,
                    "token": pve_token,
                    "secret": pve_secret,
                    "verify_ssl": bool(verify_ssl),
                },
                "netbox": {
                    "url": get_plugin_config("netbox_url", ""),
                    "token": get_plugin_config("netbox_token", ""),
                },
                "settings": {
                    "cluster_name": netbox_cluster,
                    "site_name": site_name,
                    "cluster_type": cluster_type,
                },
            }
        ],
        "telegram": {
            "enabled": bool(
                get_plugin_config("telegram_bot_token", "")
                and get_plugin_config("telegram_chat_id", "")
            ),
            "bot_token": get_plugin_config("telegram_bot_token", ""),
            "chat_id": get_plugin_config("telegram_chat_id", ""),
        },
        "monitoring": {
            "node_offline_alert": True,
            "config_drift_alert": True,
            "tag_change_alert": True,
            "resource_alert": {
                "enabled": True,
                "memory_threshold": 85,
                "cpu_threshold": 90,
                "disk_threshold": 10,
            },
        },
        "sync": {
            "incremental": True,
            "force_full_sync": False,
            "batch_size": 50,
            "default_node_role": get_plugin_config(
                "default_node_role", "PVE"
            ),
            "default_node_type": get_plugin_config(
                "default_node_type", "Standard Server"
            ),
        },
        "state_db": {
            "path": get_plugin_config(
                "state_db_path", "/var/lib/pve-sync/state.db"
            ),
            "cleanup_days": 90,
        },
    }


def write_runtime_config_file(cluster_name="default"):
    """Write a temporary YAML config file and set env vars.

    Returns:
        str: path to the temporary config file (caller must clean up)

    Raises:
        ConfigValidationError: if required config values are missing.
    """
    config_data = build_runtime_config_from_db(cluster_name)
    validate_config(config_data)

    config_file = tempfile.NamedTemporaryFile(
        "w", prefix="pve-sync-", suffix=".yaml", delete=False
    )
    with config_file:
        yaml.safe_dump(config_data, config_file, allow_unicode=True, sort_keys=False)

    _apply_runtime_env(config_file.name, config_data)
    return config_file.name


def _apply_runtime_env(config_path, config_data):
    """Set environment variables expected by the standalone sync engine."""
    os.environ["PVE_SYNC_CONFIG_FILE"] = config_path
    cluster = config_data["clusters"][0]
    pve = cluster["pve"]
    netbox = cluster["netbox"]
    telegram = config_data.get("telegram", {})

    os.environ["PVE_API_HOST"] = str(pve.get("host", ""))
    os.environ["PVE_API_USER"] = str(pve.get("user", ""))
    os.environ["PVE_API_TOKEN"] = str(pve.get("token", ""))
    os.environ["PVE_API_SECRET"] = str(pve.get("secret", ""))
    os.environ["PVE_API_VERIFY_SSL"] = (
        "true" if pve.get("verify_ssl") else "false"
    )
    os.environ["NB_API_URL"] = str(netbox.get("url", ""))
    os.environ["NB_API_TOKEN"] = str(netbox.get("token", ""))
    os.environ["TELEGRAM_BOT_TOKEN"] = str(telegram.get("bot_token", ""))
    os.environ["TELEGRAM_CHAT_ID"] = str(telegram.get("chat_id", ""))


def cleanup_runtime_env():
    """Remove temporary environment variables set by _apply_runtime_env.

    Must be called in a finally block after sync completes to prevent
    env var pollution across RQ worker invocations.
    """
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
