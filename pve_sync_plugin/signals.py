"""
PVE Sync Plugin Signals
在 VM 創建時自動建立備份狀態記錄
"""

from django.apps import apps
from django.db.models.signals import post_save
from django.dispatch import receiver


def get_vm_model():
    return apps.get_model('virtualization', 'VirtualMachine')


def _ensure_backup_status(sender, instance, created, **kwargs):
    if not created:
        return
    from .models import PveBackupStatus
    PveBackupStatus.objects.get_or_create(vm=instance)


def register_signals():
    VirtualMachine = get_vm_model()
    post_save.connect(_ensure_backup_status, sender=VirtualMachine, weak=False)
