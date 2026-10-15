"""Forms for the PVE Sync plugin UI."""

from django import forms

from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from utilities.forms.fields import DynamicModelChoiceField, DynamicModelMultipleChoiceField

from dcim.models import Device, Site
from virtualization.models import Cluster, ClusterType, VirtualMachine

from .choices import (
    BackupStatusChoices,
    DriftTypeChoices,
    SyncJobStatusChoices,
    SyncJobTriggerChoices,
    SyncScheduleChoices,
    VeeamResultChoices,
    WebhookEventChoices,
)
from .models import (
    PbsBackupStatus,
    PbsServerConfig,
    PveClusterConfig,
    PveDriftEvent,
    PvePluginSettings,
    PveSyncJob,
    PveWebhookEvent,
    VeeamBackupStatus,
    VeeamServerConfig,
)


# ---------------------------------------------------------------------------
# Model Forms (create / edit)
# ---------------------------------------------------------------------------

class PvePluginSettingsForm(NetBoxModelForm):
    """Editable singleton settings for plugin-wide defaults."""

    netbox_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True),
    )
    telegram_bot_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True),
    )
    webhook_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True),
    )

    class Meta:
        model = PvePluginSettings
        fields = (
            "netbox_url",
            "netbox_token",
            "telegram_bot_token",
            "telegram_chat_id",
            "telegram_chat_id_backup",
            "webhook_secret",
            "backup_watch_tag",
            "backup_ignore_tag",
            "sync_failure_alert_count",
            "default_cluster_name",
            "default_netbox_cluster",
            "default_site",
            "default_cluster_type",
            "default_node_role",
            "default_node_type",
            "state_db_path",
            "enable_backup_sync",
        )
        labels = {
            "sync_failure_alert_count": "同步連續失敗告警次數",
        }
        help_texts = {
            "netbox_url": "NetBox base URL (e.g. https://netbox.example.com)",
            "netbox_token": "NetBox API token with write permissions",
            "telegram_bot_token": "Telegram bot token for notifications (optional)",
            "telegram_chat_id": (
                "Telegram chat/group ID for notifications (optional). "
                "For group chats, the ID must start with a minus sign, e.g. -1002581073501"
            ),
            "telegram_chat_id_backup": (
                "Dedicated chat/group ID for backup-overdue alerts (optional). "
                "Leave blank to route these into the chat ID above instead."
            ),
            "webhook_secret": "HMAC shared secret for PVE webhook signature verification",
            "backup_watch_tag": (
                "VM tag that opts a VM into backup-overdue monitoring (case-insensitive). "
                "Leave blank to disable backup-overdue alerts entirely."
            ),
            "backup_ignore_tag": (
                "VM tag that excludes a VM from backup-overdue checks entirely "
                "(case-insensitive) — for VMs that don't need backups."
            ),
            "state_db_path": "Path to SQLite state database for incremental sync",
            "sync_failure_alert_count": "PBS / Veeam 同步連續失敗幾次就告警，恢復後會再通知一次（0 = 不告警）",
        }

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        # Invalidate cached settings so new values take effect immediately
        from .utils import clear_plugin_config_cache

        clear_plugin_config_cache()
        return instance


class _BackupSettingsForm(forms.ModelForm):
    """Edits a few PvePluginSettings fields on a page of their own."""

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        from .utils import clear_plugin_config_cache

        clear_plugin_config_cache()
        return instance


class PbsBackupSettingsForm(_BackupSettingsForm):
    backup_clusters_pbs = DynamicModelMultipleChoiceField(
        queryset=Cluster.objects.all(),
        required=False,
        label="監控叢集",
        help_text="只監控這些叢集的 VM（不選 = 全部叢集）",
    )

    class Meta:
        model = PvePluginSettings
        fields = ("backup_clusters_pbs", "backup_overdue_days_pbs")
        labels = {
            "backup_overdue_days_pbs": "備份逾期天數",
        }
        help_texts = {
            "backup_overdue_days_pbs": "PBS 超過幾天沒有新備份視為逾期（0 = 不檢查）",
        }


class VeeamBackupSettingsForm(_BackupSettingsForm):
    backup_clusters_veeam = DynamicModelMultipleChoiceField(
        queryset=Cluster.objects.all(),
        required=False,
        label="監控叢集",
        help_text="只監控這些叢集的 VM（不選 = 全部叢集）",
    )

    class Meta:
        model = PvePluginSettings
        fields = ("backup_clusters_veeam", "backup_overdue_days_veeam", "veeam_job_not_run_hours", "veeam_repo_free_percent")
        labels = {
            "backup_overdue_days_veeam": "備份逾期天數",
            "veeam_job_not_run_hours": "任務未執行告警（小時）",
            "veeam_repo_free_percent": "Repository 剩餘空間告警（%）",
        }
        help_texts = {
            "backup_overdue_days_veeam": "Veeam 超過幾天沒有新還原點視為逾期（0 = 不檢查）",
            "veeam_job_not_run_hours": (
                "已啟用的 Veeam 備份任務超過幾小時沒有執行就告警（0 = 不檢查）。"
                "每日任務建議 26，每週任務請設大於 168。"
            ),
            "veeam_repo_free_percent": "Veeam Repository 剩餘空間低於幾 % 就告警（0 = 不檢查）",
        }


class PveClusterConfigForm(NetBoxModelForm):
    """Cluster configuration form using NetBox dynamic selectors."""

    pve_secret = forms.CharField(widget=forms.PasswordInput(render_value=True))

    netbox_site = DynamicModelChoiceField(
        queryset=Site.objects.all(),
        required=True,
    )
    netbox_cluster_type = DynamicModelChoiceField(
        queryset=ClusterType.objects.all(),
        required=True,
    )
    netbox_cluster = DynamicModelChoiceField(
        queryset=Cluster.objects.all(),
        required=True,
    )

    class Meta:
        model = PveClusterConfig
        fields = (
            "name",
            "description",
            "pve_host",
            "pve_user",
            "pve_token",
            "pve_secret",
            "pve_verify_ssl",
            "netbox_site",
            "netbox_cluster_type",
            "netbox_cluster",
            "enabled",
            "sync_schedule",
            "notify_on_sync",
        )
        help_texts = {
            "sync_schedule": (
                "For reference only. Use a crontab or systemd timer calling "
                "<code>manage.py pve_sync --cluster &lt;name&gt;</code> "
                "at the desired interval."
            ),
        }

    def clean(self):
        super().clean()
        # netbox_cluster is required now, so a blank value already has its
        # own "This field is required" error — skip the conflict check here
        # instead of piling a second, redundant message onto the same field.
        if not self.cleaned_data.get("netbox_cluster"):
            return

        from .sync.config_bridge import find_netbox_cluster_conflict, resolve_netbox_cluster_name

        # Each PVE cluster needs its own NetBox cluster: VMs are matched by
        # VMID inside it, so a shared one lets clusters overwrite each other.
        candidate = PveClusterConfig(pk=self.instance.pk)
        candidate.netbox_cluster = self.cleaned_data.get("netbox_cluster")
        target = resolve_netbox_cluster_name(candidate)
        conflict = find_netbox_cluster_conflict(candidate, target)
        if conflict:
            message = f"NetBox 叢集「{target}」已被 PVE 叢集「{conflict.name}」使用，請選擇其他叢集。"
            self.add_error("netbox_cluster", message)


# ---------------------------------------------------------------------------
# Filter Forms (list view sidebar filters)
# ---------------------------------------------------------------------------

class PveSyncJobFilterForm(NetBoxModelFilterSetForm):
    """Filter form displayed in the PveSyncJob list view sidebar."""

    model = PveSyncJob

    status = forms.MultipleChoiceField(
        choices=SyncJobStatusChoices.choices,
        required=False,
    )
    trigger = forms.MultipleChoiceField(
        choices=SyncJobTriggerChoices.choices,
        required=False,
    )
    cluster_name = forms.CharField(required=False)


class PveWebhookEventFilterForm(NetBoxModelFilterSetForm):
    """Filter form for webhook event list views."""

    model = PveWebhookEvent

    event_type = forms.MultipleChoiceField(
        choices=WebhookEventChoices.choices,
        required=False,
    )
    processed = forms.NullBooleanField(required=False)


class PveClusterConfigFilterForm(NetBoxModelFilterSetForm):
    """Filter form for cluster config list views."""

    model = PveClusterConfig

    enabled = forms.NullBooleanField(required=False)
    sync_schedule = forms.MultipleChoiceField(
        choices=SyncScheduleChoices.choices,
        required=False,
    )


class PbsServerConfigForm(NetBoxModelForm):
    """PBS server configuration form."""

    pbs_token_secret = forms.CharField(
        widget=forms.PasswordInput(render_value=True),
    )
    netbox_site = DynamicModelChoiceField(
        queryset=Site.objects.all(),
        required=False,
    )
    netbox_device = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        required=False,
        label="NetBox Device",
        help_text="這台 PBS 的實體設備；留空時同步會依節點名稱自動尋找並關聯",
    )

    class Meta:
        model = PbsServerConfig
        fields = (
            "name",
            "description",
            "pbs_host",
            "pbs_token_name",
            "pbs_token_secret",
            "pbs_verify_ssl",
            "pbs_node_name",
            "netbox_site",
            "netbox_device",
            "enabled",
            "sync_schedule",
        )
        help_texts = {
            "sync_schedule": (
                "For reference only. Use a crontab or systemd timer to run "
                "PBS sync at the desired interval."
            ),
        }


class PveDriftEventFilterForm(NetBoxModelFilterSetForm):
    """Filter form for drift event list views."""

    model = PveDriftEvent

    drift_type = forms.MultipleChoiceField(
        choices=DriftTypeChoices.choices,
        required=False,
    )
    cluster_name = forms.CharField(required=False, label="叢集名稱")
    notified_telegram = forms.NullBooleanField(required=False, label="已通知 Telegram")


class PbsServerConfigFilterForm(NetBoxModelFilterSetForm):
    """Filter form for PBS server config list views."""

    model = PbsServerConfig

    enabled = forms.NullBooleanField(required=False)


class VeeamServerConfigForm(NetBoxModelForm):
    """Veeam B&R server configuration form."""

    password = forms.CharField(
        widget=forms.PasswordInput(render_value=True),
    )
    netbox_device = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        required=False,
        label="NetBox Device",
        help_text="Veeam 裝在實體機時選這裡",
    )
    netbox_vm = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
        label="NetBox Virtual Machine",
        help_text="Veeam 裝在 VM 時選這裡；兩者都留空會依 Host IP 自動尋找",
    )

    class Meta:
        model = VeeamServerConfig
        fields = (
            "name",
            "description",
            "host",
            "winrm_port",
            "winrm_use_https",
            "winrm_verify_ssl",
            "username",
            "password",
            "netbox_device",
            "netbox_vm",
            "enabled",
            "sync_schedule",
        )
        help_texts = {
            "username": (
                "Windows account that can log on over WinRM and run the Veeam PowerShell "
                "module — a dedicated read-only account is recommended."
            ),
            "sync_schedule": (
                "Picked up by the <code>run_scheduled_syncs</code> cron job. Each sync takes "
                "about a minute (loading the Veeam module is slow)."
            ),
        }


class VeeamServerConfigFilterForm(NetBoxModelFilterSetForm):
    """Filter form for Veeam server config list views."""

    model = VeeamServerConfig

    enabled = forms.NullBooleanField(required=False)


class PbsBackupStatusFilterForm(NetBoxModelFilterSetForm):
    """Filter form for per-server PBS backup list views."""

    model = PbsBackupStatus

    server_id = forms.ModelMultipleChoiceField(
        queryset=PbsServerConfig.objects.all(),
        required=False,
        label="PBS Server",
    )
    stale = forms.NullBooleanField(required=False, label="Stale (overdue)")
    monitored = forms.NullBooleanField(required=False, label="Monitored (watch tag)")


class VeeamBackupStatusFilterForm(NetBoxModelFilterSetForm):
    """Filter form for Veeam backup status list views."""

    model = VeeamBackupStatus

    server_id = forms.ModelMultipleChoiceField(
        queryset=VeeamServerConfig.objects.all(),
        required=False,
        label="Veeam Server",
    )
    last_result = forms.MultipleChoiceField(
        choices=VeeamResultChoices.choices,
        required=False,
    )
    stale = forms.NullBooleanField(required=False, label="Stale (overdue)")
    problem = forms.NullBooleanField(required=False, label="Stale or failed")
