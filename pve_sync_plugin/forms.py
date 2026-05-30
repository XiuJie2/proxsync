"""Forms for the PVE Sync plugin UI."""

from django import forms

from .models import PveClusterConfig


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
