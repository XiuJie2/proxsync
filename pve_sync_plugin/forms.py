"""Forms for the PVE Sync plugin UI."""

from django import forms

from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from utilities.forms.fields import DynamicModelChoiceField

from dcim.models import Site
from virtualization.models import Cluster, ClusterType

from .choices import (
    BackupStatusChoices,
    DriftTypeChoices,
    SyncJobStatusChoices,
    SyncJobTriggerChoices,
    SyncScheduleChoices,
    WebhookEventChoices,
)
from .models import PbsServerConfig, PveClusterConfig, PveDriftEvent, PvePluginSettings, PveSyncJob, PveWebhookEvent


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
            "webhook_secret",
            "default_cluster_name",
            "default_netbox_cluster",
            "default_site",
            "default_cluster_type",
            "default_node_role",
            "default_node_type",
            "state_db_path",
            "enable_backup_sync",
        )
        help_texts = {
            "netbox_url": "NetBox base URL (e.g. https://netbox.example.com)",
            "netbox_token": "NetBox API token with write permissions",
            "telegram_bot_token": "Telegram bot token for notifications (optional)",
            "telegram_chat_id": (
                "Telegram chat/group ID for notifications (optional). "
                "For group chats, the ID must start with a minus sign, e.g. -1002581073501"
            ),
            "webhook_secret": "HMAC shared secret for PVE webhook signature verification",
            "state_db_path": "Path to SQLite state database for incremental sync",
        }

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        # Invalidate cached settings so new values take effect immediately
        from .utils import clear_plugin_config_cache

        clear_plugin_config_cache()
        return instance


class PveClusterConfigForm(NetBoxModelForm):
    """Cluster configuration form using NetBox dynamic selectors."""

    pve_secret = forms.CharField(widget=forms.PasswordInput(render_value=True))

    netbox_site = DynamicModelChoiceField(
        queryset=Site.objects.all(),
        required=False,
    )
    netbox_cluster_type = DynamicModelChoiceField(
        queryset=ClusterType.objects.all(),
        required=False,
    )
    netbox_cluster = DynamicModelChoiceField(
        queryset=Cluster.objects.all(),
        required=False,
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
        )
        help_texts = {
            "sync_schedule": (
                "For reference only. Use a crontab or systemd timer calling "
                "<code>manage.py pve_sync --cluster &lt;name&gt;</code> "
                "at the desired interval."
            ),
        }


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
