"""Template extensions injected into NetBox core object pages."""

from netbox.plugins import PluginTemplateExtension

from .models import PveClusterConfig, PveSyncJob, PveVmTaskLog


class VirtualMachineSyncButton(PluginTemplateExtension):
    """Add a PVE sync action to NetBox virtual machine detail pages."""

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

        recent_job = (
            PveSyncJob.objects.filter(
                details__vm_id=vm.pk,
            )
            .order_by("-start_time")
            .first()
        )

        return self.render(
            "pve_sync/inc/vm_sync_button.html",
            extra_context={
                "vm": vm,
                "cluster_config": cluster_config,
                "recent_pve_sync_job": recent_job,
            },
        )


class VmTaskLogPanel(PluginTemplateExtension):
    """Inject a VM operation history panel into NetBox VM detail pages."""

    models = ["virtualization.virtualmachine"]

    def full_width_page(self):
        vm = self.context["object"]

        if not vm.serial:
            return ""

        try:
            vmid = int(vm.serial)
        except (ValueError, TypeError):
            return ""

        qs = PveVmTaskLog.objects.filter(vmid=vmid)
        cluster_config = None
        if vm.cluster_id:
            cluster_config = PveClusterConfig.objects.filter(
                netbox_cluster_id=vm.cluster_id, enabled=True,
            ).first()
        if cluster_config:
            qs = qs.filter(cluster_name=cluster_config.name)

        task_logs = qs.order_by("-start_time")[:30]

        return self.render(
            "pve_sync/inc/vm_task_log_panel.html",
            extra_context={"task_logs": task_logs, "vmid": vmid},
        )


template_extensions = [VirtualMachineSyncButton, VmTaskLogPanel]
