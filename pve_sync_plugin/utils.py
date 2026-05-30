"""
PVE Sync Plugin Utilities
辅助函数
"""

from django.conf import settings
import os


def get_plugin_config(key, default=None):
    """
    从 NetBox 插件配置获取设置
    
    优先级:
    1. NetBox 插件配置 (通过插件系统)
    2. 环境变量
    3. 默认值
    """
    # 尝试从 NetBox 插件配置获取（需要插件已加载）
    try:
        from .plugin import PveSyncPluginConfig
        # 实际实现中，配置通过插件系统提供
        # 这里先使用环境变量作为回退
    except:
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
    }
    
    env_key = env_mapping.get(key)
    if env_key and os.environ.get(env_key):
        value = os.environ[env_key]
        if key == 'pve_api_verify_ssl':
            return value.lower() == 'true'
        return value
    
    return default


def init_scheduler():
    """初始化定时任务调度器（如果需要独立于 Celery）"""
    # 可以在这里启动 APScheduler 或 Celery beat
    pass
