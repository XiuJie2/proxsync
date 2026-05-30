"""
PVE Sync Plugin Celery Tasks
异步任务处理：同步、Webhook处理、备份检查
"""

from celery import shared_task, current_task
from django.utils import timezone
import logging
import time

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='pve_sync_plugin.tasks.sync_pve_to_netbox')
def sync_pve_to_netbox(self, cluster_name='default'):
    """
    异步执行 PVE → NetBox 同步
    
    Args:
        cluster_name: 集群名称，'default' 表示单集群模式
    """
    from .models import PveSyncJob
    
    job_id = self.request.id or f"sync-{int(time.time())}"
    start_time = timezone.now()
    
    # 创建或更新任务记录
    job = PveSyncJob.objects.create(
        cluster_name=cluster_name,
        status='running',
        trigger='scheduled' if self.request.called_directly else 'api',
        details={
            'celery_task_id': self.request.id,
            'worker': self.request.hostname,
        }
    )
    
    logger.info(f"开始同步任务: {job_id}, 集群: {cluster_name}")
    
    try:
        # 导入增强同步器
        from sync import OptimizedPVEToNetBoxSync
        
        # 创建同步实例（支持增强模式）
        sync = OptimizedPVEToNetBoxSync()
        
        # 如果是多集群模式，需要加载对应集群配置
        if hasattr(sync, 'cluster_name'):
            # 已经通过 config.py 初始化
            pass
        else:
            # 基础模式，使用环境变量
            pass
        
        # 执行同步
        sync.sync()
        
        # 更新任务状态
        job.status = 'success'
        job.end_time = timezone.now()
        job.total_vms = sync.stats.get('total_vms', 0)
        job.success_vms = sync.stats.get('success_vms', 0)
        job.failed_vms = job.total_vms - job.success_vms
        job.nodes_offline = sync.stats.get('nodes_offline', 0)
        job.config_drifts = sync.stats.get('config_drifts_detected', 0)
        job.tag_changes = sync.stats.get('tag_changes', 0)
        job.resource_alerts = sync.stats.get('resources_alert', 0)
        job.save()
        
        logger.info(f"同步任务完成: {job_id}, 成功 {job.success_vms}/{job.total_vms}")
        
        return {
            'status': 'success',
            'job_id': job.id,
            'cluster': cluster_name,
            'total_vms': job.total_vms,
            'success_vms': job.success_vms,
            'duration': job.duration,
        }
        
    except Exception as e:
        logger.error(f"同步任务失败: {job_id}, 错误: {e}", exc_info=True)
        
        job.status = 'failed'
        job.end_time = timezone.now()
        job.details['error'] = str(e)
        job.save()
        
        # 重试逻辑（最多3次）
        if self.request.retries < 3:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        
        return {
            'status': 'failed',
            'job_id': job.id,
            'error': str(e),
        }


@shared_task(bind=True, name='pve_sync_plugin.tasks.process_webhook')
def process_webhook_event(self, event_id):
    """
    异步处理 PVE Webhook 事件
    
    Args:
        event_id: PveWebhookEvent 记录 ID
    """
    from .models import PveWebhookEvent, PveSyncJob
    
    try:
        event = PveWebhookEvent.objects.get(id=event_id)
        
        # 标记为处理中
        if event.processed:
            logger.info(f"事件 {event_id} 已处理，跳过")
            return {'status': 'skipped', 'reason': 'already processed'}
        
        logger.info(f"处理 webhook 事件: {event.event_type}, VM: {event.vm_name}")
        
        # 根据事件类型决定同步策略
        trigger_sync = False
        sync_cluster = 'default'
        
        event_mapping = {
            'vm-started': True,
            'vm-stopped': True,
            'vm-migrated': True,
            'node-online': False,  # 只记录状态，不同步
            'node-offline': False,
            'backup-done': True,  # 可以触发备份状态同步
            'backup-failed': True,
            'configuration-change': True,
        }
        
        should_sync = trigger_sync or event_mapping.get(event.event_type, False)
        
        if should_sync:
            # 触发增量同步（只同步受影响的 VM）
            task = sync_pve_to_netbox.delay(
                cluster_name=sync_cluster,
                vm_filter={'vmid': event.vmid} if event.vmid else None
            )
            
            event.sync_job = PveSyncJob.objects.filter(
                details__celery_task_id=task.id
            ).first()
        
        # 标记为已处理
        event.mark_processed(sync_job=event.sync_job)
        
        return {
            'status': 'processed',
            'event_id': event_id,
            'event_type': event.event_type,
            'sync_triggered': should_sync,
            'sync_task_id': event.sync_job.details.get('celery_task_id') if event.sync_job else None,
        }
        
    except PveWebhookEvent.DoesNotExist:
        logger.error(f"Webhook 事件不存在: {event_id}")
        return {'status': 'error', 'message': 'Event not found'}
    except Exception as e:
        logger.error(f"处理 webhook 失败: {event_id}, 错误: {e}", exc_info=True)
        
        # 标记为失败
        try:
            event = PveWebhookEvent.objects.get(id=event_id)
            event.mark_processed(error=str(e))
        except:
            pass
            
        return {'status': 'error', 'message': str(e)}


@shared_task(name='pve_sync_plugin.tasks.check_backup_status')
def check_backup_status():
    """
    定时任务：检查所有 VM 的备份状态
    从 PVE API 获取最新备份信息，更新 PveBackupStatus 模型
    """
    from .utils import get_plugin_config
    from pynetbox import api as pynetbox_api
    from proxmoxer import ProxmoxAPI
    
    logger.info("开始检查备份状态...")
    
    try:
        # 连接到 PVE
        pve = ProxmoxAPI(
            host=get_plugin_config('pve_api_host'),
            user=get_plugin_config('pve_api_user'),
            token_name=get_plugin_config('pve_api_token'),
            token_value=get_plugin_config('pve_api_secret'),
            verify_ssl=get_plugin_config('pve_api_verify_ssl', False),
        )
        
        # 连接到 NetBox
        nb = pynetbox_api(
            url=get_plugin_config('netbox_url', 'http://localhost:8000'),
            token=get_plugin_config('netbox_token', ''),
        )
        
        # 遍历所有 VM
        nodes = pve.nodes.get()
        backup_updates = 0
        
        for node in nodes:
            node_name = node['node']
            try:
                vms = pve.nodes(node_name).qemu.get()
                for vm in vms:
                    vmid = vm['vmid']
                    
                    # 查询备份（这里假设使用 vzdump 标准路径）
                    # 实际实现需要根据 PVE 备份配置调整
                    backup_info = check_vm_backup(pve, node_name, vmid)
                    
                    if backup_info:
                        # 更新或创建备份状态记录
                        try:
                            nb_vm = nb.virtualization.virtual_machines.get(
                                cf_vm_id=vmid  # 通过 custom field 查找
                            )
                            if nb_vm:
                                backup_status, created = PveBackupStatus.objects.get_or_create(
                                    vm=nb_vm
                                )
                                backup_status.last_backup = backup_info['timestamp']
                                backup_status.backup_size = backup_info.get('size', 0)
                                backup_status.backup_status = 'success'
                                backup_status.backup_path = backup_info.get('path', '')
                                backup_status.save()
                                backup_updates += 1
                        except Exception as e:
                            logger.warning(f"更新 VM {vmid} 备份状态失败: {e}")
                            
            except Exception as e:
                logger.error(f"检查节点 {node_name} 失败: {e}")
                continue
        
        logger.info(f"备份状态检查完成，更新 {backup_updates} 台 VM")
        return {'status': 'success', 'updates': backup_updates}
        
    except Exception as e:
        logger.error(f"备份状态检查失败: {e}", exc_info=True)
        raise


def check_vm_backup(pve, node_name, vmid):
    """
    检查单个 VM 的最新备份
    返回字典: {'timestamp': datetime, 'size': int, 'path': str} 或 None
    """
    # TODO: 根据实际 PVE 备份配置实现
    # 可以通过以下方式:
    # 1. 读取 vzdump 日志文件
    # 2. 查询备份存储 (pve.nodes(node_name).storage('backup').content.get())
    # 3. 使用 PVE API 的 backup 相关端点（如果有）
    
    # 这里返回模拟数据
    return None
