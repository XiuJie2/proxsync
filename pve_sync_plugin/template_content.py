"""Template extensions injected into NetBox core object pages."""

try:
    from netbox.plugins import PluginTemplateExtension
except ImportError:  # NetBox 3.x compatibility
    from extras.plugins import PluginTemplateExtension

from .models import PveClusterConfig, PveSyncJob


class VirtualMachineSyncButton(PluginTemplateExtension):
    """Add a PVE sync action to NetBox virtual machine detail pages."""

    model = "virtualization.virtualmachine"
    models = ["virtualization.virtualmachine"]

    def buttons(self):
        request = self.context.get("request")
        if request and not request.user.has_perm("pve_sync_plugin.add_pvesyncjob"):
            return ""

        vm = self.context["object"]
        cluster_config = None
        if getattr(vm, "cluster_id", None):
            cluster_config = PveClusterConfig.objects.filter(
                netbox_cluster_id=vm.cluster_id,
                enabled=True,
            ).first()

        recent_job = PveSyncJob.objects.filter(
            details__vm_id=vm.pk,
        ).order_by("-start_time").first()

        return self.render(
            "pve_sync/inc/vm_sync_button.html",
            extra_context={
                "vm": vm,
                "cluster_config": cluster_config,
                "recent_pve_sync_job": recent_job,
            },
        )


template_extensions = [VirtualMachineSyncButton]
