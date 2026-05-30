"""
PVE Sync Plugin URLs
URL 路由配置
"""

from django.urls import path
from django.contrib.auth.decorators import login_required
from . import views

app_name = "pve_sync_plugin"

urlpatterns = [
    # 仪表板
    path('', login_required(views.sync_dashboard), name='dashboard'),
    path('trigger/', views.trigger_sync_view, name='trigger-sync'),
    path('virtual-machines/<int:vm_id>/sync/', views.trigger_vm_sync_view, name='trigger-vm-sync'),
    path('settings/', views.plugin_settings, name='settings'),
    path('clusters/', views.cluster_config_list, name='cluster-list'),
    path('clusters/add/', views.cluster_config_add, name='cluster-add'),
    path('clusters/<int:pk>/edit/', views.cluster_config_edit, name='cluster-edit'),
    
    # API 端点
    path('api/trigger/', views.trigger_sync, name='api-trigger'),
    path('api/status/<int:job_id>/', views.sync_status, name='api-status'),
    path('api/jobs/', views.list_sync_jobs, name='api-jobs'),
    path('api/backup-status/', views.backup_status_list, name='api-backup-list'),
    path('api/backup-status/<int:vm_id>/', views.update_backup_status, name='api-backup-update'),
    
    # Webhook 接收器（对外公开，需签名验证）
    path('webhook/', views.webhook_receiver, name='webhook'),
]
