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
    VeeamResultChoices,
    VmTaskTypeChoices,
    WebhookEventChoices,
)
from .fields import EncryptedTextField, mask_secrets


class SecretMaskMixin:
    """Keep credentials out of NetBox's changelog snapshots."""

    secret_fields = ()

    def serialize_object(self, exclude=None):
        return mask_secrets(super().serialize_object(exclude=exclude), self.secret_fields)


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
    def is_veeam_job(self):
        return self.cluster_name.startswith("veeam:")

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
        from .utils import get_threshold

        if not self.last_backup:
            return True
        days = get_threshold("backup_overdue_days_pbs")
        return bool(days) and self.backup_age_days > days


class PbsBackupStatus(NetBoxModel):
    """Latest backup of one VM on one PBS server.

    PveBackupStatus keeps only the newest backup across all PBS servers; this
    keeps each server's own copy so every server can be listed and checked.
    """

    vm = models.ForeignKey(
        "virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="pbs_backup_statuses",
    )
    server = models.ForeignKey(
        "PbsServerConfig",
        on_delete=models.CASCADE,
        related_name="backup_statuses",
    )
    last_backup = models.DateTimeField(null=True, blank=True)
    backup_size = models.BigIntegerField(null=True, blank=True)
    backup_path = models.CharField(max_length=500, blank=True)
    pve_backup_id = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["vm__name"]
        constraints = [
            models.UniqueConstraint(fields=["vm", "server"], name="pbsbackupstatus_unique_vm_server"),
        ]
        verbose_name = "PBS Backup Status"
        verbose_name_plural = "PBS Backup Statuses"

    def __str__(self):
        return f"{self.vm.name} @ {self.server.name}"

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:pbsbackupstatus", args=[self.pk])

    @property
    def backup_age_days(self):
        if self.last_backup:
            return (timezone.now() - self.last_backup).days
        return None

    @property
    def is_stale(self):
        from .utils import get_threshold

        if not self.last_backup:
            return True
        days = get_threshold("backup_overdue_days_pbs")
        return bool(days) and self.backup_age_days > days


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


class PvePluginSettings(SecretMaskMixin, NetBoxModel):
    """Singleton settings editable from the NetBox Web UI."""

    secret_fields = ("netbox_token", "telegram_bot_token", "webhook_secret")

    netbox_url = models.URLField(blank=True)
    netbox_token = models.CharField(max_length=200, blank=True)

    telegram_bot_token = models.CharField(max_length=200, blank=True)
    telegram_chat_id = models.CharField(max_length=100, blank=True)
    telegram_chat_id_backup = models.CharField(
        max_length=100, blank=True,
        help_text="備份異常通知專用群組（留空則沿用上方的一般通知 Chat ID）",
    )
    webhook_secret = models.CharField(max_length=200, blank=True)

    backup_watch_tag = models.CharField(
        max_length=50, default="0N", blank=True,
        help_text="VM 標籤：有此標籤的 VM 才會被監控備份逾期（留空則停用備份逾期監控）",
    )
    backup_ignore_tag = models.CharField(
        max_length=50, default="NO-Backup", blank=True,
        help_text="VM 標籤：有此標籤的 VM 一律忽略備份逾期檢查（不需要備份）",
    )
    backup_overdue_days_pbs = models.PositiveIntegerField(
        default=7,
        help_text="PBS 超過幾天沒有新備份視為逾期（0 = 不檢查）",
    )
    backup_overdue_days_veeam = models.PositiveIntegerField(
        default=7,
        help_text="Veeam 超過幾天沒有新還原點視為逾期（0 = 不檢查）",
    )
    backup_clusters_pbs = models.ManyToManyField(
        "virtualization.Cluster", blank=True, related_name="+",
        help_text="只監控這些叢集的 VM 的 PBS 備份逾期（不選 = 全部叢集）",
    )
    backup_clusters_veeam = models.ManyToManyField(
        "virtualization.Cluster", blank=True, related_name="+",
        help_text="只監控這些叢集的 VM 的 Veeam 備份逾期（不選 = 全部叢集）",
    )
    veeam_job_not_run_hours = models.PositiveIntegerField(
        default=26,
        help_text="已啟用的 Veeam 備份任務超過幾小時沒有執行就告警（0 = 不檢查）",
    )
    veeam_repo_free_percent = models.PositiveIntegerField(
        default=10,
        help_text="Veeam Repository 剩餘空間低於幾 % 就告警（0 = 不檢查）",
    )
    sync_failure_alert_count = models.PositiveIntegerField(
        default=2,
        help_text="PBS / Veeam 同步連續失敗幾次就告警（0 = 不告警）",
    )

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


class PveClusterConfig(SecretMaskMixin, NetBoxModel):
    secret_fields = ("pve_secret",)

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    pve_host = models.CharField(max_length=200)
    pve_user = models.CharField(max_length=100)
    pve_token = models.CharField(max_length=100)
    pve_secret = EncryptedTextField()
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


class PbsServerConfig(SecretMaskMixin, NetBoxModel):
    """Proxmox Backup Server connection configuration."""

    secret_fields = ("pbs_token_secret",)

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
    pbs_token_secret = EncryptedTextField()
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
    netbox_device = models.ForeignKey(
        "dcim.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pbs_server_configs",
        help_text="The NetBox device of this PBS host (found by node name when left empty)",
    )
    enabled = models.BooleanField(default=True)
    sync_schedule = models.CharField(
        max_length=20,
        choices=SyncScheduleChoices,
        default=SyncScheduleChoices.DISABLED,
    )
    last_sync = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=20, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    failure_alerted = models.BooleanField(default=False)

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


def find_netbox_host(host):
    """Return (device, vm) in NetBox that owns ``host`` (an IP or a name).

    Used to link a backup server config to the NetBox object of the machine
    it runs on. Either or both may be None.
    """
    import ipaddress

    from dcim.models import Device
    from ipam.models import IPAddress
    from virtualization.models import VirtualMachine

    host = (host or "").strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/")[0]
    if host.count(":") == 1:
        host = host.split(":")[0]
    if not host:
        return None, None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        device = Device.objects.filter(name__iexact=host).first()
        vm = None if device else VirtualMachine.objects.filter(name__iexact=host).first()
        return device, vm

    for ip in IPAddress.objects.filter(address__net_host=host):
        parent = getattr(ip.assigned_object, "parent_object", None)
        if isinstance(parent, Device):
            return parent, None
        if isinstance(parent, VirtualMachine):
            return None, parent
    return None, None


class VeeamServerConfig(SecretMaskMixin, NetBoxModel):
    """Veeam Backup & Replication server, read over WinRM + Veeam PowerShell.

    Community Edition blocks the job/session endpoints of the VBR REST API,
    so job results are collected by running the Veeam PowerShell module on
    the server instead.
    """

    secret_fields = ("password",)

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    host = models.CharField(
        max_length=200,
        help_text="Veeam B&R server hostname or IP",
    )
    winrm_port = models.PositiveIntegerField(default=5985)
    winrm_use_https = models.BooleanField(
        default=False,
        help_text="Use WinRM over HTTPS (usually port 5986)",
    )
    winrm_verify_ssl = models.BooleanField(default=False)
    username = models.CharField(
        max_length=150,
        help_text="Windows account allowed to log on over WinRM (e.g. Administrator or DOMAIN\\user)",
    )
    password = EncryptedTextField()
    netbox_device = models.ForeignKey(
        "dcim.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="veeam_server_configs",
        help_text="Physical NetBox device running Veeam (found by IP when left empty)",
    )
    netbox_vm = models.ForeignKey(
        "virtualization.VirtualMachine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="veeam_server_configs",
        help_text="NetBox virtual machine running Veeam (found by IP when left empty)",
    )
    enabled = models.BooleanField(default=True)
    sync_schedule = models.CharField(
        max_length=20,
        choices=SyncScheduleChoices,
        default=SyncScheduleChoices.DISABLED,
    )
    last_sync = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=20, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    failure_alerted = models.BooleanField(default=False)
    server_info = models.JSONField(default=dict, blank=True)
    job_summary = models.JSONField(
        default=list,
        blank=True,
        help_text="Last session of every backup job, as of the last sync",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Veeam Server Config"
        verbose_name_plural = "Veeam Server Configs"

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
        return reverse("plugins:pve_sync_plugin:veeamserverconfig", args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.netbox_device_id and not self.netbox_vm_id:
            self.netbox_device, self.netbox_vm = find_netbox_host(self.host)
        super().save(*args, **kwargs)

    @property
    def netbox_object(self):
        return self.netbox_device or self.netbox_vm

    @property
    def license(self):
        return (self.server_info or {}).get("license") or {}

    @property
    def license_full(self):
        lic = self.license
        return bool(lic.get("licensed")) and lic.get("used", 0) >= lic.get("licensed")

    @property
    def repositories(self):
        return (self.server_info or {}).get("repositories") or []

    @property
    def winrm_url(self):
        scheme = "https" if self.winrm_use_https else "http"
        return f"{scheme}://{self.host}:{self.winrm_port}/wsman"

    @property
    def failed_jobs(self):
        return [j for j in self.job_summary or [] if j.get("result") in ("failed", "warning")]


class VeeamBackupStatus(NetBoxModel):
    """Latest Veeam backup of one VM on one Veeam server.

    Kept apart from PveBackupStatus (PBS) so both sources are shown and
    checked separately.
    """

    vm = models.ForeignKey(
        "virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="veeam_backup_statuses",
    )
    server = models.ForeignKey(
        "VeeamServerConfig",
        on_delete=models.CASCADE,
        related_name="backup_statuses",
    )
    job_name = models.CharField(max_length=200, blank=True)
    last_result = models.CharField(
        max_length=20,
        choices=VeeamResultChoices,
        default=VeeamResultChoices.UNKNOWN,
        help_text="Result of this VM in the job's last session",
    )
    last_run_start = models.DateTimeField(null=True, blank=True)
    last_run_end = models.DateTimeField(null=True, blank=True)
    last_run_reason = models.TextField(blank=True)
    last_restore_point = models.DateTimeField(null=True, blank=True)
    restore_point_type = models.CharField(max_length=50, blank=True)
    restore_point_consistent = models.BooleanField(null=True, blank=True)
    veeam_object_id = models.CharField(max_length=100, blank=True)
    in_job = models.BooleanField(
        null=True,
        blank=True,
        help_text="Whether a backup job on this server includes the VM (empty = unknown)",
    )

    class Meta:
        ordering = ["vm__name"]
        constraints = [
            models.UniqueConstraint(fields=["vm", "server"], name="veeambackupstatus_unique_vm_server"),
        ]
        verbose_name = "Veeam Backup Status"
        verbose_name_plural = "Veeam Backup Statuses"

    def __str__(self):
        return f"{self.vm.name} @ {self.server.name} - {self.last_result}"

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:veeambackupstatus", args=[self.pk])

    def get_last_result_color(self):
        return {
            "success": "success",
            "warning": "warning",
            "failed": "danger",
            "running": "primary",
        }.get(self.last_result, "secondary")

    @property
    def backup_age_days(self):
        if self.last_restore_point:
            return (timezone.now() - self.last_restore_point).days
        return None

    @property
    def is_stale(self):
        if not self.last_restore_point:
            return True
        days = self.overdue_days
        return bool(days) and self.backup_age_days > days

    @property
    def overdue_days(self):
        from .utils import veeam_overdue_days

        return veeam_overdue_days(self.job_name)

    @property
    def has_problem(self):
        # A VM no longer in any job here is not expected to be backed up here.
        if self.in_job is False:
            return False
        return self.is_stale or self.last_result == VeeamResultChoices.FAILED


class VmProvisioningLog(NetBoxModel):
    """Planning record created in the VM Provisioning Planner before PVE sync."""

    STATUS_CHOICES = [
        ("planning",  "規劃中"),
        ("completed", "完成"),
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
    created_by       = models.CharField(max_length=150, blank=True, verbose_name="創建人")

    class Meta:
        ordering = ["-created"]
        verbose_name = "VM Provisioning Log"

    def __str__(self):
        vmid_str = f" (VMID {self.vmid})" if self.vmid else ""
        return f"{self.vm_name}{vmid_str}"

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:vmprovisioninglog", args=[self.pk])

    def get_status_color(self):
        """Named get_{field}_color so NetBox's ChoiceFieldColumn picks it up for table badges."""
        return {"planning": "info", "completed": "success"}.get(self.status, "secondary")

    @property
    def status_badge(self):
        return self.get_status_color()

    QEMU_GA_ITEMS = [
        ("chk_qemu_options", "在 VM Options 啟用 QEMU Guest Agent"),
        ("chk_qemu_install", "安裝 qemu-guest-agent 套件"),
        ("chk_qemu_enable",  "啟用並啟動 qemu-guest-agent 服務"),
    ]

    OS_TYPE_CHOICES = [
        "Ubuntu 22.04 LTS",
        "Ubuntu 24.04 LTS",
        "Debian 12",
        "Rocky Linux 9",
        "AlmaLinux 9",
        "Windows Server 2022",
    ]


class PveVmTaskLog(NetBoxModel):
    """Records VM lifecycle operations fetched from PVE task history."""

    upid         = models.CharField(max_length=300, unique=True, verbose_name="UPID")
    vmid         = models.IntegerField(verbose_name="VM ID")
    vm_name      = models.CharField(max_length=200, blank=True, verbose_name="VM 名稱")
    cluster_name = models.CharField(max_length=100, verbose_name="叢集")
    node         = models.CharField(max_length=100, verbose_name="節點")
    task_type    = models.CharField(max_length=30, choices=VmTaskTypeChoices, verbose_name="操作類型")
    operator     = models.CharField(max_length=200, verbose_name="操作者")
    start_time   = models.DateTimeField(verbose_name="開始時間")
    end_time     = models.DateTimeField(null=True, blank=True, verbose_name="結束時間")
    status       = models.TextField(blank=True, verbose_name="狀態")
    notified_telegram = models.BooleanField(default=False, verbose_name="已通知")

    NOTIFY_TYPES = {"qmdestroy", "qmclone", "qmrestore"}

    TASK_ICONS = {
        "qmcreate":   ("mdi mdi-plus-circle",   "success"),
        "qmdestroy":  ("mdi mdi-delete",         "danger"),
        "qmclone":    ("mdi mdi-content-copy",   "info"),
        "qmmigrate":  ("mdi mdi-transfer",       "warning"),
        "qmrestore":  ("mdi mdi-restore",        "primary"),
        "vzdump":     ("mdi mdi-backup-restore", "secondary"),
        "qmstart":    ("mdi mdi-play-circle",    "success"),
        "qmstop":     ("mdi mdi-stop-circle",    "danger"),
        "qmshutdown": ("mdi mdi-power",          "warning"),
        "qmreboot":   ("mdi mdi-restart",        "info"),
    }

    class Meta:
        ordering = ["-start_time"]
        indexes = [
            models.Index(fields=["vmid", "cluster_name"]),
            models.Index(fields=["task_type"]),
            models.Index(fields=["operator"]),
            models.Index(fields=["start_time"]),
        ]
        verbose_name = "VM Task Log"
        verbose_name_plural = "VM Task Logs"

    def __str__(self):
        return f"{self.get_task_type_display()} — {self.vm_name} (VMID {self.vmid}) by {self.operator}"

    def get_absolute_url(self):
        return reverse("plugins:pve_sync_plugin:pvevmtasklog_list")

    @property
    def task_icon(self):
        return self.TASK_ICONS.get(self.task_type, ("mdi mdi-history", "secondary"))

    @property
    def status_ok(self):
        return self.status == "OK"
