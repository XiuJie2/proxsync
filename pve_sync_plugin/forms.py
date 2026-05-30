"""Forms for the PVE Sync plugin UI."""

from django import forms

from .models import PveClusterConfig, PvePluginSettings


class PvePluginSettingsForm(forms.ModelForm):
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


class PveClusterConfigForm(forms.ModelForm):
    """Basic cluster configuration form for NetBox's plugin UI."""

    pve_secret = forms.CharField(widget=forms.PasswordInput(render_value=True))

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
