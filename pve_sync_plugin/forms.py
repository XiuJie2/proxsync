"""Forms for the PVE Sync plugin UI."""

from django import forms

from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from utilities.forms.fields import DynamicModelChoiceField

from dcim.models import Site
from virtualization.models import Cluster, ClusterType

from .choices import (
    BackupStatusChoices,
    SyncJobStatusChoices,
    SyncJobTriggerChoices,
    SyncScheduleChoices,
    WebhookEventChoices,
)
from .models import PveClusterConfig, PvePluginSettings, PveSyncJob, PveWebhookEvent


# ---------------------------------------------------------------------------
# Model Forms (create / edit)
# ---------------------------------------------------------------------------

class PvePluginSettingsForm(NetBoxModelForm):
    """Editable singleton settings for plugin-wide defaults."""

    pve_api_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True),
    )
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
            "pve_api_host",
            "pve_api_user",
            "pve_api_token",
            "pve_api_secret",
            "pve_api_verify_ssl",
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
