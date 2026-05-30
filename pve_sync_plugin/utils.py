"""
PVE Sync Plugin Utilities
辅助函数
"""

import os


def get_plugin_config(key, default=None):
    """
    从 NetBox 插件配置获取设置
    
    优先级:
    1. NetBox Web GUI settings stored in the plugin database table
    2. NetBox PLUGINS_CONFIG
    3. 环境变量
    4. 默认值
    """
    try:
        from .models import PvePluginSettings

        settings = PvePluginSettings.objects.filter(pk=1).first()
        if settings is not None and hasattr(settings, key):
            value = getattr(settings, key)
            if isinstance(value, bool):
                return value
            if value not in (None, ""):
                return value
    except Exception:
        pass

    try:
        from netbox.plugins import get_plugin_config as netbox_get_plugin_config

        value = netbox_get_plugin_config("pve_sync_plugin", key)
        if value not in (None, ""):
            return value
    except Exception:
        pass
    
    # 环境变量映射
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
    }
    
    env_key = env_mapping.get(key)
    if env_key and os.environ.get(env_key):
        value = os.environ[env_key]
        if key == 'pve_api_verify_ssl':
            return value.lower() == 'true'
        return value
    
    return default
