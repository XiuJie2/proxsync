"""
PVE Sync Plugin Views
提供 REST API 和页面视图
"""

from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes as drf_permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
import json
import hmac
import hashlib

from .models import PveSyncJob, PveWebhookEvent, PveBackupStatus, PveClusterConfig
from .tasks import enqueue_sync, enqueue_webhook_event
from .utils import get_plugin_config


@login_required
@permission_required('pve_sync_plugin.view_pvesyncjob', raise_exception=True)
def sync_dashboard(request):
    """同步仪表板页面"""
    recent_jobs = PveSyncJob.objects.all()[:50]
    pending_webhooks = PveWebhookEvent.objects.filter(processed=False).count()
    backup_alerts = PveBackupStatus.objects.filter(
        last_backup__lt=timezone.now() - timezone.timedelta(days=7)
    ).count()
    
    context = {
        'recent_jobs': recent_jobs,
        'pending_webhooks': pending_webhooks,
        'backup_alerts': backup_alerts,
        'clusters': PveClusterConfig.objects.filter(enabled=True),
    }
    return render(request, 'pve_sync/dashboard.html', context)


@login_required
@permission_required('pve_sync_plugin.add_pvesyncjob', raise_exception=True)
@require_http_methods(["GET", "POST"])
def trigger_sync_view(request):
    """Web GUI endpoint for manually starting a sync."""
    cluster_name = request.POST.get("cluster") or request.GET.get("cluster") or "default"
    try:
        job = _create_and_enqueue_sync_job(cluster_name, request.user, "manual")
        messages.success(request, f"PVE 同步已排入背景任務，Job #{job.id}")
    except Exception as exc:
        messages.error(request, f"無法啟動同步: {exc}")
    return redirect(reverse("plugins:pve_sync_plugin:dashboard"))


@api_view(['POST'])
@drf_permission_classes([IsAuthenticated])
def trigger_sync(request):
    """
    手动触发同步
    
    POST /api/plugins/pve-sync/trigger/
    
    Body:
    {
        "cluster": "cluster_name"  # 可选，不指定则同步所有集群
    }
    """
    try:
        cluster_name = request.data.get('cluster', 'default')
        job = _create_and_enqueue_sync_job(cluster_name, request.user, "api")
        
        return Response({
            'status': 'success',
            'message': f'同步任务已启动 (集群: {cluster_name})',
            'job_id': job.id,
            'rq_job_id': job.details.get('rq_job_id'),
        }, status=status.HTTP_202_ACCEPTED)
        
    except Exception as e:
        return Response({
            'status': 'error',
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@drf_permission_classes([IsAuthenticated])
def sync_status(request, job_id):
    """
    查询同步任务状态
    
    GET /api/plugins/pve-sync/status/{job_id}/
    """
    try:
        job = get_object_or_404(PveSyncJob, id=job_id)
        
        data = {
            'id': job.id,
            'cluster': job.cluster_name,
            'status': job.get_status_display(),
            'start_time': job.start_time,
            'end_time': job.end_time,
            'duration': job.duration,
            'total_vms': job.total_vms,
            'success_vms': job.success_vms,
            'failed_vms': job.failed_vms,
            'success_rate': job.success_rate,
            'trigger': job.get_trigger_display(),
            'triggered_by': job.triggered_by.username if job.triggered_by else None,
            'details': job.details,
        }
        
        return Response(data)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@drf_permission_classes([IsAuthenticated])
def list_sync_jobs(request):
    """
    列出最近的同步任务
    
    GET /api/plugins/pve-sync/jobs/?limit=20&cluster=default
    """
    limit = int(request.GET.get('limit', 20))
    cluster = request.GET.get('cluster')
    
    jobs = PveSyncJob.objects.all()
    if cluster:
        jobs = jobs.filter(cluster_name=cluster)
    
    jobs = jobs[:limit]
    
    data = [{
        'id': job.id,
        'cluster': job.cluster_name,
        'status': job.get_status_display(),
        'start_time': job.start_time,
        'end_time': job.end_time,
        'total_vms': job.total_vms,
        'success_vms': job.success_vms,
        'success_rate': job.success_rate,
        'trigger': job.get_trigger_display(),
    } for job in jobs]
    
    return Response(data)


@csrf_exempt
@require_http_methods(["POST"])
def webhook_receiver(request):
    """
    接收 PVE Webhook 事件
    
    POST /api/plugins/pve-sync/webhook/
    
    Headers:
        X-PVE-Signature: <hmac_sha256_signature>  # 如果配置了 secret
    
    Body (JSON):
    {
        "event": "vm-started",
        "node": "pve01",
        "vmid": 100,
        "vmname": "web01",
        "timestamp": "2025-03-30T15:30:00Z"
    }
    """
    try:
        # 读取原始 body（用于签名验证）
        raw_body = request.body.decode('utf-8')
        data = json.loads(raw_body)
        
        # 验证签名（如果配置了 secret）
        webhook_secret = get_plugin_config('webhook_secret')
        if webhook_secret:
            signature = request.headers.get('X-PVE-Signature', '')
            expected = hmac.new(
                webhook_secret.encode(),
                raw_body.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid signature'
                }, status=status.HTTP_403_FORBIDDEN)
        
        # 保存 webhook 事件
        event = PveWebhookEvent.objects.create(
            event_type=data.get('event', 'unknown'),
            node=data.get('node'),
            vmid=data.get('vmid'),
            vm_name=data.get('vmname'),
            raw_data=data
        )
        
        rq_job_id = enqueue_webhook_event(event)
        
        return JsonResponse({
            'status': 'success',
            'message': 'Webhook received',
            'event_id': event.id,
            'rq_job_id': rq_job_id,
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@drf_permission_classes([IsAuthenticated])
def backup_status_list(request):
    """
    列出备份状态异常的 VM
    
    GET /api/plugins/pve-sync/backup-status/?stale_only=true
    """
    stale_only = request.GET.get('stale_only', 'false').lower() == 'true'
    
    queryset = PveBackupStatus.objects.all()
    if stale_only:
        queryset = queryset.filter(
            last_backup__lt=timezone.now() - timezone.timedelta(days=7)
        )
    
    # 关联虚拟机信息
    from django.db.models import F
    
    data = []
    for backup in queryset.select_related('vm'):
        vm = backup.vm
        data.append({
            'vm_id': vm.id,
            'vm_name': vm.name,
            'last_backup': backup.last_backup,
            'backup_status': backup.get_backup_status_display(),
            'backup_age_days': backup.backup_age_days,
            'is_stale': backup.is_stale,
            'next_backup': backup.next_backup,
        })
    
    return Response(data)


@api_view(['POST'])
@drf_permission_classes([IsAuthenticated])
def update_backup_status(request, vm_id):
    """
    手动更新 VM 备份状态（用于测试或手动干预）
    
    POST /api/plugins/pve-sync/backup-status/{vm_id}/
    
    Body:
    {
        "status": "success",
        "last_backup": "2025-03-30T15:30:00Z",
        "backup_size": 1073741824,
        "backup_path": "/storage/backup/vm-100.vma.gz"
    }
    """
    from virtualization.models import VirtualMachine
    
    vm = get_object_or_404(VirtualMachine, pk=vm_id)
    
    backup_status, created = PveBackupStatus.objects.get_or_create(vm=vm)
    
    status_val = request.data.get('status')
    if status_val in dict(PveBackupStatus._meta.get_field('backup_status').choices):
        backup_status.backup_status = status_val
    
    if 'last_backup' in request.data:
        backup_status.last_backup = request.data['last_backup']
    
    if 'backup_size' in request.data:
        backup_status.backup_size = request.data['backup_size']
    
    if 'backup_path' in request.data:
        backup_status.backup_path = request.data['backup_path']
    
    backup_status.save()
    
    return Response({
        'status': 'success',
        'message': f'Backup status updated for {vm.name}',
    })


def _create_and_enqueue_sync_job(cluster_name, user, trigger):
    if cluster_name != 'default':
        get_object_or_404(PveClusterConfig, name=cluster_name, enabled=True)

    job = PveSyncJob.objects.create(
        cluster_name=cluster_name,
        status='pending',
        trigger=trigger,
        triggered_by=user if getattr(user, "is_authenticated", False) else None,
        details={},
    )
    enqueue_sync(job)
    job.refresh_from_db()
    return job
