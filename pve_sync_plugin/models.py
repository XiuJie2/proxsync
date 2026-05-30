"""
PVE Sync Plugin Models
数据模型：同步任务、Webhook 事件、备份状态
"""

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import json


class PveSyncJob(models.Model):
    """PVE 同步任务记录"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('partial', 'Partial Success'),
    ]
    
    cluster_name = models.CharField(
        max_length=100,
        default='default',
        help_text="同步的集群名称"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    # 统计信息
    total_vms = models.IntegerField(default=0)
    success_vms = models.IntegerField(default=0)
    failed_vms = models.IntegerField(default=0)
    
    # 检测统计
    nodes_offline = models.IntegerField(default=0)
    config_drifts = models.IntegerField(default=0)
    tag_changes = models.IntegerField(default=0)
    resource_alerts = models.IntegerField(default=0)
    
    # 详细信息（JSON）
    details = models.JSONField(default=dict, blank=True)
    
    # 触发方式
    TRIGGER_CHOICES = [
        ('manual', 'Manual'),
        ('scheduled', 'Scheduled'),
        ('webhook', 'Webhook'),
        ('api', 'API Call'),
    ]
    trigger = models.CharField(
        max_length=20,
        choices=TRIGGER_CHOICES,
        default='manual'
    )
    
    # 触发用户（如果是手动触发）
    triggered_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pve_sync_jobs'
    )
    
    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['status', 'start_time']),
            models.Index(fields=['cluster_name']),
        ]
    
    def __str__(self):
        return f"{self.cluster_name} - {self.get_status_display()} ({self.start_time})"
    
    @property
    def duration(self):
        """任务耗时（秒）"""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def success_rate(self):
        """成功率"""
        if self.total_vms > 0:
            return (self.success_vms / self.total_vms) * 100
        return 0


class PveWebhookEvent(models.Model):
    """PVE Webhook 事件记录"""
    
    EVENT_CHOICES = [
        ('vm-started', 'VM Started'),
        ('vm-stopped', 'VM Stopped'),
        ('vm-migrated', 'VM Migrated'),
        ('node-online', 'Node Online'),
        ('node-offline', 'Node Offline'),
        ('backup-done', 'Backup Completed'),
        ('backup-failed', 'Backup Failed'),
        ('configuration-change', 'Configuration Change'),
    ]
    
    event_type = models.CharField(max_length=50, choices=EVENT_CHOICES)
    node = models.CharField(max_length=100, null=True, blank=True)
    vmid = models.IntegerField(null=True, blank=True)
    vm_name = models.CharField(max_length=200, null=True, blank=True)
    
    # 事件原始数据（JSON）
    raw_data = models.JSONField(default=dict)
    
    # 处理状态
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)
    
    # 同步任务关联（如果触发了同步）
    sync_job = models.ForeignKey(
        'PveSyncJob',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events'
    )
    
    received_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['event_type', 'processed']),
            models.Index(fields=['vmid']),
            models.Index(fields=['received_at']),
        ]
    
    def __str__(self):
        return f"{self.event_type} - {self.vm_name or self.node} ({self.received_at})"
    
    def mark_processed(self, sync_job=None, error=None):
        """标记为已处理"""
        self.processed = True
        self.processed_at = timezone.now()
        if sync_job:
            self.sync_job = sync_job
        if error:
            self.processing_error = error
        self.save()


class PveBackupStatus(models.Model):
    """VM 备份状态记录（同步到 NetBox Custom Field）"""
    
    vm = models.OneToOneField(
        'virtualization.VirtualMachine',
        on_delete=models.CASCADE,
        related_name='pve_backup_status'
    )
    
    last_backup = models.DateTimeField(null=True, blank=True)
    backup_size = models.BigIntegerField(null=True, blank=True, help_text="字节")
    backup_status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Success'),
            ('failed', 'Failed'),
            ('running', 'Running'),
            ('unknown', 'Unknown'),
        ],
        default='unknown'
    )
    backup_path = models.CharField(max_length=500, blank=True)
    next_backup = models.DateTimeField(null=True, blank=True)
    
    # 从 PVE 同步的原始信息
    pve_backup_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "PVE Backup Status"
        verbose_name_plural = "PVE Backup Statuses"
    
    def __str__(self):
        return f"{self.vm.name} - {self.backup_status}"
    
    @property
    def backup_age_days(self):
        """备份天数（如果存在）"""
        if self.last_backup:
            delta = timezone.now() - self.last_backup
            return delta.days
        return None
    
    @property
    def is_stale(self, max_age_days=7):
        """备份是否过期"""
        if not self.last_backup:
            return True
        return self.backup_age_days > max_age_days


class PvePluginSettings(models.Model):
    """Singleton settings editable from the NetBox Web UI."""

    pve_api_host = models.CharField(max_length=200, blank=True)
    pve_api_user = models.CharField(max_length=100, default="root@pam")
    pve_api_token = models.CharField(max_length=100, blank=True)
    pve_api_secret = models.CharField(max_length=200, blank=True)
    pve_api_verify_ssl = models.BooleanField(default=False)

    netbox_url = models.URLField(blank=True)
    netbox_token = models.CharField(max_length=200, blank=True)

    telegram_bot_token = models.CharField(max_length=200, blank=True)
    telegram_chat_id = models.CharField(max_length=100, blank=True)
    webhook_secret = models.CharField(max_length=200, blank=True)

    default_cluster_name = models.CharField(max_length=100, default="default")
    default_netbox_cluster = models.CharField(max_length=100, default="Proxmox Cluster")
    default_site = models.CharField(max_length=100, default="Main Datacenter")
    default_cluster_type = models.CharField(max_length=100, default="Proxmox")
    default_node_role = models.CharField(max_length=100, default="PVE")
    default_node_type = models.CharField(max_length=100, default="Standard Server")

    state_db_path = models.CharField(max_length=500, default="/var/lib/netbox/pve-sync-state.db")
    enable_backup_sync = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "PVE Sync Settings"
        verbose_name_plural = "PVE Sync Settings"

    def __str__(self):
        return "PVE Sync Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings


class PveClusterConfig(models.Model):
    """多集群配置"""
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    
    # PVE 连接配置
    pve_host = models.CharField(max_length=200)
    pve_user = models.CharField(max_length=100)
    pve_token = models.CharField(max_length=100)
    pve_secret = models.CharField(max_length=200)  # 加密存储
    pve_verify_ssl = models.BooleanField(default=False)
    
    # NetBox 关联
    netbox_site = models.ForeignKey(
        'dcim.Site',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pve_clusters'
    )
    netbox_cluster_type = models.ForeignKey(
        'virtualization.ClusterType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    netbox_cluster = models.ForeignKey(
        'virtualization.Cluster',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pve_sync_config'
    )
    
    # 同步配置
    enabled = models.BooleanField(default=True)
    sync_schedule = models.CharField(
        max_length=20,
        choices=[
            ('disabled', 'Disabled'),
            ('hourly', 'Hourly'),
            ('every_6h', 'Every 6 hours'),
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
        ],
        default='disabled'
    )
    
    # 统计
    last_sync = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=20, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @property
    def is_active(self):
        """是否启用且最近同步成功"""
        if not self.enabled:
            return False
        if not self.last_sync:
            return False
        # 检查最近24小时内是否成功同步
        recent = timezone.now() - timezone.timedelta(hours=24)
        return self.last_sync > recent and self.last_sync_status == 'success'
