"""
PVE-NetBox Sync Plugin
NetBox 插件：在 NetBox UI 中提供 PVE 同步功能和 Webhook 接收
"""

from netbox.plugins import PluginConfig

__version__ = "1.0.0"


class PveSyncPluginConfig(PluginConfig):
    """PVE Sync 插件配置"""

    name = "pve_sync_plugin"
    verbose_name = "PVE-NetBox 同步"
    description = "将 Proxmox VE 环境同步到 NetBox，支持实时 Webhook 和手动触发"
    author = "Your Name"
    author_email = "your.email@example.com"
    version = __version__
    
    # 指定 Django app
    django_apps = [
        "pve_sync_plugin",
    ]
    
    # 需要的中介软件
    middleware = []
    
    # 需要Celery任务（异步同步）
    celery_tasks = [
        "pve_sync_plugin.tasks.sync_pve_to_netbox",
        "pve_sync_plugin.tasks.process_webhook",
    ]
    
    # 静态文件和模板
    static_files = "static"
    templates = "templates"
    
    # 自定义视图和 API
    views = [
        "pve_sync_plugin.views.SyncView",
        "pve_sync_plugin.views.WebhookView",
        "pve_sync_plugin.views.BackupStatusView",
    ]
    
    # 配置参数（用户可在 NetBox 插件配置页面设置）
    config = {
        "pve_api_host": {
            "type": "string",
            "required": True,
            "description": "PVE API 主机地址",
            "default": "",
        },
        "pve_api_user": {
            "type": "string",
            "required": True,
            "description": "PVE API 用户名",
            "default": "root@pam",
        },
        "pve_api_token": {
            "type": "string",
            "required": True,
            "description": "PVE API Token 名称",
            "default": "",
        },
        "pve_api_secret": {
            "type": "password",  # 密码类型，加密存储
            "required": True,
            "description": "PVE API Token Secret",
            "default": "",
        },
        "pve_api_verify_ssl": {
            "type": "boolean",
            "required": False,
            "description": "是否验证 SSL 证书",
            "default": False,
        },
        "webhook_secret": {
            "type": "password",
            "required": False,
            "description": "PVE Webhook 签名密钥（可选）",
            "default": "",
        },
        "sync_schedule": {
            "type": "choice",
            "choices": [
                ("disabled", "Disabled"),
                ("hourly", "Hourly"),
                ("every_6h", "Every 6 hours"),
                ("daily", "Daily"),
                ("weekly", "Weekly"),
            ],
            "required": False,
            "description": "自动同步频率",
            "default": "disabled",
        },
        "enable_backup_sync": {
            "type": "boolean",
            "required": False,
            "description": "启用备份状态同步",
            "default": True,
        },
    }

    def ready(self):
        """插件加载完成后的初始化"""
        import pve_sync_plugin.signals  # noqa: F401
        import pve_sync_plugin.templatetags  # noqa: F401

        # 初始化任务队列
        from pve_sync_plugin.utils import init_scheduler
        init_scheduler()

        print("✓ PVE Sync Plugin 已加载")
