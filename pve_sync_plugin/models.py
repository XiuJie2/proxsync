import datetime

from django.db import models
from django.urls import reverse
from django.utils import timezone

from netbox.models import NetBoxModel

from .choices import (
    BackupStatusChoices,
    DriftTypeChoices,
    SyncJobStatusChoices,
    SyncJobTriggerChoices,
    SyncScheduleChoices,
    WebhookEventChoices,
)


class PveSyncJob(NetBoxModel):
    cluster_name = models.CharField(
        max_length=100,
        default="default",
        help_text="同步的集群名称",
    )
    status = models.CharField(
        max_length=20,
        choices=SyncJobStatusChoices,
        default=SyncJobStatusChoices.STATUS_PENDING,
    )
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    total_vms = models.IntegerField(default=0)
    success_vms = models.IntegerField(default=0)
    failed_vms = models.IntegerField(default=0)

    nodes_offline = models.IntegerField(default=0)
    config_drifts = models.IntegerField(default=0)
    tag_changes = models.IntegerField(default=0)
    resource_alerts = models.IntegerField(default=0)

    details = models.JSONField(default=dict, blank=True)

    trigger = models.CharField(
        max_length=20,
        choices=SyncJobTriggerChoices,
        default=SyncJobTriggerChoices.TRIGGER_MANUAL,
    )

    triggered_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pve_sync_jobs",
    )

    class Meta:
        ordering = ["-start_time"]
        indexes = [
            models.Index(fields=["status", "start_time"]),
            models.Index(fields=["cluster_name"]),
        ]
        verbose_name = "Proxmox Sync Job"
        verbose_name_plural = "Proxmox Sync Jobs"

    def __str__(self):
        return f"{self.cluster_name} - {self.get_status_display()} ({self.start_time})"

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:pvesyncjob", args=[self.pk])

    @property
    def duration(self):
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def success_rate(self):
        if self.total_vms > 0:
            return (self.success_vms / self.total_vms) * 100
        return 0

    @property
    def status_badge(self):
        """Return CSS class for status badges in templates."""
        return {
            "pending": "info",
            "running": "primary",
            "success": "success",
            "failed": "danger",
            "partial": "warning",
        }.get(self.status, "secondary")

    @property
    def is_pbs_job(self):
        return self.cluster_name.startswith("pbs:")

    @property
    def error_message(self):
        if not self.details:
            return ""
        return self.details.get("error") or self.details.get("queue_error") or ""


class PveWebhookEvent(NetBoxModel):
    event_type = models.CharField(max_length=50, choices=WebhookEventChoices)
    node = models.CharField(max_length=100, null=True, blank=True)
    vmid = models.IntegerField(null=True, blank=True)
    vm_name = models.CharField(max_length=200, null=True, blank=True)

    raw_data = models.JSONField(default=dict)

    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)

    sync_job = models.ForeignKey(
        "PveSyncJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_events",
    )

    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["event_type", "processed"]),
            models.Index(fields=["vmid"]),
            models.Index(fields=["received_at"]),
        ]
        verbose_name = "PVE Webhook Event"
        verbose_name_plural = "PVE Webhook Events"

    def __str__(self):
        return f"{self.event_type} - {self.vm_name or self.node} ({self.received_at})"

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:pvewebhookevent", args=[self.pk])

    def mark_processed(self, sync_job=None, error=None):
        self.processed = True
        self.processed_at = timezone.now()
        if sync_job:
            self.sync_job = sync_job
        if error:
            self.processing_error = error
        self.save()


class PveBackupStatus(NetBoxModel):
    vm = models.OneToOneField(
        "virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="pve_backup_status",
    )

    last_backup = models.DateTimeField(null=True, blank=True)
    backup_size = models.BigIntegerField(null=True, blank=True, help_text="字节")
    backup_status = models.CharField(
        max_length=20,
        choices=BackupStatusChoices,
        default=BackupStatusChoices.STATUS_UNKNOWN,
    )
    backup_path = models.CharField(max_length=500, blank=True)
    next_backup = models.DateTimeField(null=True, blank=True)

    pve_backup_id = models.CharField(max_length=100, unique=True, null=True, blank=True)

    class Meta:
        verbose_name = "PVE Backup Status"
        verbose_name_plural = "PVE Backup Statuses"

    def __str__(self):
        return f"{self.vm.name} - {self.backup_status}"

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:pvebackupstatus", args=[self.pk])

    @property
    def backup_age_days(self):
        if self.last_backup:
            delta = timezone.now() - self.last_backup
            return delta.days
        return None

    @property
    def is_stale(self):
        if not self.last_backup:
            return True
        return self.backup_age_days > 7


class PveDriftEvent(NetBoxModel):
    """Records a single configuration drift event detected during sync."""

    vm_name = models.CharField(max_length=200)
    vmid = models.IntegerField()
    cluster_name = models.CharField(max_length=100)
    drift_type = models.CharField(max_length=30, choices=DriftTypeChoices)
    field_name = models.CharField(max_length=100, verbose_name="欄位")
    old_value = models.TextField(blank=True, verbose_name="舊值")
    new_value = models.TextField(blank=True, verbose_name="新值")
    sync_job = models.ForeignKey(
        "PveSyncJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drift_events",
    )
    notified_telegram = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["vmid", "cluster_name"]),
            models.Index(fields=["drift_type"]),
            models.Index(fields=["created"]),
        ]
        verbose_name = "VM Drift Event"
        verbose_name_plural = "VM Drift Events"

    def __str__(self):
        return f"{self.vm_name} [{self.get_drift_type_display()}] {self.field_name}: {self.old_value} → {self.new_value}"

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:pvedriftevent", args=[self.pk])

    @property
    def drift_type_badge(self):
        return {
            "hardware": "warning",
            "migration": "info",
            "ip_change": "primary",
            "tag_change": "secondary",
            "vm_created": "success",
            "vm_deleted": "danger",
            "vm_renamed": "info",
            "disk_change": "warning",
            "description_change": "secondary",
        }.get(self.drift_type, "secondary")


class PvePluginSettings(NetBoxModel):
    """Singleton settings editable from the NetBox Web UI."""

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

    state_db_path = models.CharField(
        max_length=500,
        default="/var/lib/netbox/pve-sync-state.db",
    )
    enable_backup_sync = models.BooleanField(default=True)
    log_retention_days = models.PositiveIntegerField(
        default=90,
        help_text="保留同步 Log 及 State DB 歷史資料天數（0 = 不自動清除）",
    )

    class Meta:
        verbose_name = "Proxmox Sync Settings"
        verbose_name_plural = "Proxmox Sync Settings"

    def __str__(self):
        return "Proxmox Sync Settings"

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:settings")

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton settings row."""
        pass

    @classmethod
    def load(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings


class PveClusterConfig(NetBoxModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    pve_host = models.CharField(max_length=200)
    pve_user = models.CharField(max_length=100)
    pve_token = models.CharField(max_length=100)
    pve_secret = models.CharField(max_length=200)
    pve_verify_ssl = models.BooleanField(default=False)

    netbox_site = models.ForeignKey(
        "dcim.Site",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pve_clusters",
    )
    netbox_cluster_type = models.ForeignKey(
        "virtualization.ClusterType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    netbox_cluster = models.ForeignKey(
        "virtualization.Cluster",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pve_sync_config",
    )

    enabled = models.BooleanField(default=True)
    sync_schedule = models.CharField(
        max_length=20,
        choices=SyncScheduleChoices,
        default=SyncScheduleChoices.DISABLED,
    )
    notify_on_sync = models.BooleanField(
        default=True,
        help_text="同步時是否發送 Telegram 通知（含同步開始/完成、漂移偵測等）",
    )

    last_sync = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "PVE Cluster Config"
        verbose_name_plural = "PVE Cluster Configs"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Cascade name changes so that PveSyncJob records and plugin settings
        # stay consistent, and state_db incremental history is preserved.
        old_name = None
        if self.pk:
            try:
                old_name = (
                    PveClusterConfig.objects.filter(pk=self.pk)
                    .values_list("name", flat=True)
                    .first()
                )
            except Exception:
                pass

        super().save(*args, **kwargs)

        if old_name and old_name != self.name:
            PveSyncJob.objects.filter(cluster_name=old_name).update(cluster_name=self.name)
            PvePluginSettings.objects.filter(default_cluster_name=old_name).update(
                default_cluster_name=self.name
            )
            # Rename cluster in state_db so incremental sync stays effective.
            try:
                from state_db import StateDB
                db_path = PvePluginSettings.load().state_db_path or "/var/lib/pve-sync/state.db"
                StateDB(db_path).rename_cluster(old_name, self.name)
            except Exception:
                pass  # state_db rename is best-effort; full sync will happen if it fails

    def get_sync_schedule_color(self):
        return {
            'hourly': 'info',
            'every_3h': 'info',
            'every_6h': 'info',
            'daily': 'secondary',
            'weekly': 'secondary',
        }.get(self.sync_schedule, 'secondary')

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:pveclusterconfig", args=[self.pk])

    @property
    def is_active(self):
        if not self.enabled:
            return False
        if not self.last_sync:
            return False
        recent = timezone.now() - datetime.timedelta(hours=24)
        return self.last_sync > recent and self.last_sync_status == "success"


class PbsServerConfig(NetBoxModel):
    """Proxmox Backup Server connection configuration."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    pbs_host = models.CharField(
        max_length=200,
        help_text="PBS API URL (e.g. https://pbs01:8007)",
    )
    pbs_token_name = models.CharField(
        max_length=100,
        help_text="API token (e.g. root@pam!apitoken)",
    )
    pbs_token_secret = models.CharField(max_length=200)
    pbs_verify_ssl = models.BooleanField(default=False)
    pbs_node_name = models.CharField(
        max_length=100,
        help_text="PBS node name",
    )
    netbox_site = models.ForeignKey(
        "dcim.Site",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pbs_servers",
    )
    enabled = models.BooleanField(default=True)
    sync_schedule = models.CharField(
        max_length=20,
        choices=SyncScheduleChoices,
        default=SyncScheduleChoices.DISABLED,
    )
    last_sync = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "PBS Server Config"
        verbose_name_plural = "PBS Server Configs"

    def __str__(self):
        return self.name

    def get_sync_schedule_color(self):
        return {
            'hourly': 'info',
            'every_3h': 'info',
            'every_6h': 'info',
            'daily': 'secondary',
            'weekly': 'secondary',
        }.get(self.sync_schedule, 'secondary')

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:pbsserverconfig", args=[self.pk])

    @property
    def display_host(self):
        """Return just the hostname/IP without scheme or port."""
        host = self.pbs_host
        if '://' in host:
            host = host.split('://', 1)[1]
        host = host.split(':')[0]
        return host


class VmProvisioningLog(NetBoxModel):
    """Planning record created in the VM Provisioning Planner before PVE sync."""

    STATUS_CHOICES = [
        ("planning",     "規劃中"),
        ("in_progress",  "部署中"),
        ("completed",    "完成"),
    ]

    vm_name          = models.CharField(max_length=100, verbose_name="VM 名稱")
    vmid             = models.IntegerField(null=True, blank=True, verbose_name="VMID")
    cluster_name     = models.CharField(max_length=100, blank=True, verbose_name="叢集")
    node             = models.CharField(max_length=100, blank=True, verbose_name="節點")
    os_type          = models.CharField(max_length=50,  blank=True, verbose_name="作業系統")
    cpu              = models.IntegerField(null=True, blank=True, verbose_name="CPU")
    ram_gb           = models.IntegerField(null=True, blank=True, verbose_name="記憶體 (GB)")
    disk_gb          = models.IntegerField(null=True, blank=True, verbose_name="磁碟 (GB)")
    management_ip    = models.CharField(max_length=50,  blank=True, verbose_name="Management IP")
    management_gw    = models.CharField(max_length=50,  blank=True, verbose_name="Management 閘道")
    internet_ip      = models.CharField(max_length=50,  blank=True, verbose_name="Internet IP")
    internet_gw      = models.CharField(max_length=50,  blank=True, verbose_name="Internet 閘道")
    status           = models.CharField(max_length=20, default="planning",
                                        choices=STATUS_CHOICES, verbose_name="狀態")
    notes            = models.TextField(blank=True, verbose_name="備註")
    checklist        = models.JSONField(default=dict, blank=True, verbose_name="清單狀態")

    class Meta:
        ordering = ["-created"]
        verbose_name = "VM Provisioning Log"

    def __str__(self):
        vmid_str = f" (VMID {self.vmid})" if self.vmid else ""
        return f"{self.vm_name}{vmid_str}"

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:vmprovisioninglog", args=[self.pk])

    @property
    def status_badge(self):
        return {"planning": "info", "in_progress": "warning", "completed": "success"}.get(
            self.status, "secondary"
        )

    @property
    def checklist_progress(self):
        """Return (checked_count, total_count)."""
        if not self.checklist:
            return 0, 0
        total   = len(self.checklist)
        checked = sum(1 for v in self.checklist.values() if v)
        return checked, total
