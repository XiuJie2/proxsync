"""
PVE Sync Plugin App Config
Django App 配置
"""

from django.apps import AppConfig


class PveSyncPluginConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pve_sync_plugin'
    verbose_name = "PVE-NetBox 同步"
