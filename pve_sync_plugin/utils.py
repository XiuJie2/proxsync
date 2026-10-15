"""
PVE Sync Plugin Utilities
辅助函数
"""

import os

from django.core.cache import cache


_SETTINGS_CACHE_KEY = "pve_sync_plugin:settings"
_SETTINGS_CACHE_TTL = 60  # seconds


def get_plugin_config(key, default=None):
    """
    从 NetBox 插件配置获取设置

    优先级:
    1. NetBox Web GUI settings stored in the plugin database table (cached)
    2. NetBox PLUGINS_CONFIG
    3. 环境变量
    4. 默认值
    """
    # 1. Plugin DB settings (with cache)
    try:
        settings = cache.get(_SETTINGS_CACHE_KEY)
        if settings is None:
            from .models import PvePluginSettings

            settings = PvePluginSettings.objects.filter(pk=1).first()
            if settings is not None:
                cache.set(_SETTINGS_CACHE_KEY, settings, _SETTINGS_CACHE_TTL)

        if settings is not None and hasattr(settings, key):
            value = getattr(settings, key)
            if isinstance(value, bool):
                return value
            if value not in (None, ""):
                return value
    except Exception:
        pass

    # 2. NetBox PLUGINS_CONFIG
    try:
        from netbox.plugins import get_plugin_config as netbox_get_plugin_config

        value = netbox_get_plugin_config("pve_sync_plugin", key)
        if value not in (None, ""):
            return value
    except Exception:
        pass

    # 3. 环境变量映射
    env_mapping = {
        'pve_api_host': 'PVE_API_HOST',
        'pve_api_user': 'PVE_API_USER',
        'pve_api_token': 'PVE_API_TOKEN',
        'pve_api_secret': 'PVE_API_SECRET',
        'pve_api_verify_ssl': 'PVE_API_VERIFY_SSL',
        'webhook_secret': 'WEBHOOK_SECRET',
        'netbox_url': 'NB_API_URL',
        'netbox_token': 'NB_API_TOKEN',
        'telegram_bot_token': 'TELEGRAM_BOT_TOKEN',
        'telegram_chat_id': 'TELEGRAM_CHAT_ID',
        'telegram_chat_id_backup': 'TELEGRAM_CHAT_ID_BACKUP',
        'backup_watch_tag': 'BACKUP_WATCH_TAG',
        'backup_ignore_tag': 'BACKUP_IGNORE_TAG',
    }

    env_key = env_mapping.get(key)
    if env_key and os.environ.get(env_key):
        value = os.environ[env_key]
        if key == 'pve_api_verify_ssl':
            return value.lower() == 'true'
        return value

    return default


def clear_plugin_config_cache():
    """Invalidate the cached PvePluginSettings object.

    Call this after settings are saved from the Web UI or API
    to ensure subsequent reads pick up the new values.
    """
    cache.delete(_SETTINGS_CACHE_KEY)


# Defaults for the backup-monitoring thresholds editable on the Settings page.
BACKUP_THRESHOLD_DEFAULTS = {
    "backup_overdue_days_pbs": 7,
    "backup_overdue_days_veeam": 7,
    "veeam_job_not_run_hours": 26,
    "veeam_repo_free_percent": 10,
    "sync_failure_alert_count": 2,
}


def get_threshold(key):
    """Return an integer backup-monitoring threshold (0 = check disabled)."""
    default = BACKUP_THRESHOLD_DEFAULTS[key]
    try:
        return int(get_plugin_config(key, default))
    except (TypeError, ValueError):
        return default


def send_backup_alert(text):
    """Send an HTML Telegram message to the backup-alert chat (falls back to the
    general chat). Returns True when Telegram accepted it, None when Telegram
    is not configured."""
    import logging

    import requests

    token = get_plugin_config("telegram_bot_token", "")
    chat_id = get_plugin_config("telegram_chat_id_backup", "") or get_plugin_config("telegram_chat_id", "")
    if not token or not chat_id:
        return None
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        logging.getLogger(__name__).warning("Telegram alert failed: HTTP %s", resp.status_code)
    except Exception as exc:
        logging.getLogger(__name__).warning("Telegram alert failed: %s", exc)
    return False
