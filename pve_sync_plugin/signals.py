"""
PVE Sync Plugin Signals
信号处理：在 VM 创建/更新时做自动操作
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import PveBackupStatus


@receiver(post_save, sender='virtualization.VirtualMachine')
def ensure_backup_status(sender, instance, created, **kwargs):
    """
    确保每个 VM 都有对应的备份状态记录
    """
    # 仅在 VM 创建时
    if created:
        PveBackupStatus.objects.get_or_create(vm=instance)
