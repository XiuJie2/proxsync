"""
PVE Sync Plugin URLs
URL 路由配置
"""

from django.urls import path, include
from django.contrib.auth.decorators import login_required
from . import views

app_name = "pve_sync_plugin"

urlpatterns = [
    # 仪表板
    path('', login_required(views.sync_dashboard), name='dashboard'),
    
    # API 端点
    path('api/trigger/', views.trigger_sync, name='api-trigger'),
    path('api/status/<int:job_id>/', views.sync_status, name='api-status'),
    path('api/jobs/', views.list_sync_jobs, name='api-jobs'),
    path('api/backup-status/', views.backup_status_list, name='api-backup-list'),
    path('api/backup-status/<int:vm_id>/', views.update_backup_status, name='api-backup-update'),
    
    # Webhook 接收器（对外公开，需签名验证）
    path('webhook/', views.webhook_receiver, name='webhook'),
]
