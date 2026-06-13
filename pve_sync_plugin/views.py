from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from netbox.views import generic

import json
import hmac
import hashlib

from .filtersets import (
    PveBackupStatusFilterSet,
    PveClusterConfigFilterSet,
    PveSyncJobFilterSet,
    PveWebhookEventFilterSet,
)
from .forms import (
    PveClusterConfigFilterForm,
    PveClusterConfigForm,
    PvePluginSettingsForm,
    PveSyncJobFilterForm,
    PveWebhookEventFilterForm,
)
from .models import (
    PveBackupStatus,
    PveClusterConfig,
    PvePluginSettings,
    PveSyncJob,
    PveWebhookEvent,
)
from .tables import (
    PveBackupStatusTable,
    PveClusterConfigTable,
    PveSyncJobTable,
    PveWebhookEventTable,
)
from .tasks import enqueue_webhook_event
from .utils import get_plugin_config
from .view_helpers import (
    create_and_enqueue_sync_job,
    has_active_sync_job,
    resolve_cluster_name_for_vm,
)


# ============================================================================
# Dashboard
# ============================================================================

class DashboardView(PermissionRequiredMixin, View):
    """Main plugin dashboard with recent jobs, alerts, and quick actions."""

    permission_required = "pve_sync_plugin.view_pvesyncjob"

    def get(self, request):
        recent_jobs = PveSyncJob.objects.all()[:20]
        pending_webhooks = PveWebhookEvent.objects.filter(processed=False).count()
        backup_alerts = PveBackupStatus.objects.filter(
            last_backup__lt=timezone.now() - timezone.timedelta(days=7)
        ).count()
        clusters = PveClusterConfig.objects.filter(enabled=True)

        # Aggregate job stats in a single query instead of 3 separate ones
        job_stats = PveSyncJob.objects.aggregate(
            total=Count("id"),
            success=Count("id", filter=Q(status="success")),
            failed=Count("id", filter=Q(status="failed")),
        )

        context = {
            "recent_jobs": recent_jobs,
            "pending_webhooks": pending_webhooks,
            "backup_alerts": backup_alerts,
            "clusters": clusters,
            "total_jobs": job_stats["total"],
            "success_jobs": job_stats["success"],
            "failed_jobs": job_stats["failed"],
        }
        return render(request, "pve_sync/dashboard.html", context)


# ============================================================================
# PveSyncJob Views
# ============================================================================

class PveSyncJobListView(generic.ObjectListView):
    queryset = PveSyncJob.objects.all()
    table = PveSyncJobTable
    filterset = PveSyncJobFilterSet
    filterset_form = PveSyncJobFilterForm


class PveSyncJobView(generic.ObjectView):
    queryset = PveSyncJob.objects.all()
    template_name = "pve_sync/pvesyncjob.html"


class PveSyncJobDeleteView(generic.ObjectDeleteView):
    queryset = PveSyncJob.objects.all()


class PveSyncJobBulkDeleteView(generic.BulkDeleteView):
    queryset = PveSyncJob.objects.all()
    table = PveSyncJobTable


# ============================================================================
# PveWebhookEvent Views
# ============================================================================

class PveWebhookEventListView(generic.ObjectListView):
    queryset = PveWebhookEvent.objects.all()
    table = PveWebhookEventTable
    filterset = PveWebhookEventFilterSet
    filterset_form = PveWebhookEventFilterForm


class PveWebhookEventView(generic.ObjectView):
    queryset = PveWebhookEvent.objects.all()
    template_name = "pve_sync/pvewebhookevent.html"


class PveWebhookEventDeleteView(generic.ObjectDeleteView):
    queryset = PveWebhookEvent.objects.all()


class PveWebhookEventBulkDeleteView(generic.BulkDeleteView):
    queryset = PveWebhookEvent.objects.all()
    table = PveWebhookEventTable


# ============================================================================
# PveClusterConfig Views
# ============================================================================

class PveClusterConfigListView(generic.ObjectListView):
    queryset = PveClusterConfig.objects.select_related(
        "netbox_site", "netbox_cluster_type", "netbox_cluster"
    )
    table = PveClusterConfigTable
    filterset = PveClusterConfigFilterSet
    filterset_form = PveClusterConfigFilterForm


class PveClusterConfigView(generic.ObjectView):
    queryset = PveClusterConfig.objects.all()
    template_name = "pve_sync/pveclusterconfig.html"


class PveClusterConfigEditView(generic.ObjectEditView):
    queryset = PveClusterConfig.objects.all()
    form = PveClusterConfigForm


class PveClusterConfigDeleteView(generic.ObjectDeleteView):
    queryset = PveClusterConfig.objects.all()


class PveClusterConfigBulkDeleteView(generic.BulkDeleteView):
    queryset = PveClusterConfig.objects.all()
    table = PveClusterConfigTable


# ============================================================================
# PveBackupStatus Views
# ============================================================================

class PveBackupStatusListView(generic.ObjectListView):
    queryset = PveBackupStatus.objects.select_related("vm")
    table = PveBackupStatusTable
    filterset = PveBackupStatusFilterSet


class PveBackupStatusView(generic.ObjectView):
    queryset = PveBackupStatus.objects.all()
    template_name = "pve_sync/pvebackupstatus.html"


# ============================================================================
# Plugin Settings (singleton)
# ============================================================================

class PvePluginSettingsView(PermissionRequiredMixin, View):
    """Edit singleton plugin settings from the NetBox Web UI."""

    permission_required = "pve_sync_plugin.change_pvepluginsettings"

    def get(self, request):
        settings_obj = PvePluginSettings.load()
        form = PvePluginSettingsForm(instance=settings_obj)
        return render(request, "pve_sync/settings.html", {"form": form})

    def post(self, request):
        settings_obj = PvePluginSettings.load()
        form = PvePluginSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "PVE Sync settings updated.")
            return redirect(reverse("plugins:pve_sync_plugin:settings"))
        return render(request, "pve_sync/settings.html", {"form": form})


# ============================================================================
# Sync Triggers
# ============================================================================

class TriggerSyncView(PermissionRequiredMixin, View):
    """Web GUI endpoint for manually starting a sync."""

    permission_required = "pve_sync_plugin.add_pvesyncjob"

    def post(self, request):
        cluster_name = request.POST.get("cluster") or "default"

        # Prevent duplicate sync jobs for the same cluster
        if has_active_sync_job(cluster_name):
            messages.warning(
                request,
                f"Cluster '{cluster_name}' already has an active sync job. Please try again later.",
            )
            return redirect(reverse("plugins:pve_sync_plugin:dashboard"))

        try:
            job = create_and_enqueue_sync_job(cluster_name, request.user, "manual")
            messages.success(request, f"PVE sync queued as background job #{job.id}.")
            return redirect(job.get_absolute_url())
        except Exception as exc:
            messages.error(request, f"Unable to start sync: {exc}")
        return redirect(reverse("plugins:pve_sync_plugin:dashboard"))

    def get(self, request):
        messages.info(request, "Use Sync Now from the dashboard to start a sync.")
        return redirect(reverse("plugins:pve_sync_plugin:dashboard"))


class TriggerVmSyncView(PermissionRequiredMixin, View):
    """Queue a sync from a VM detail page."""

    permission_required = "pve_sync_plugin.add_pvesyncjob"

    def post(self, request, vm_id):
        from virtualization.models import VirtualMachine

        vm = get_object_or_404(VirtualMachine, pk=vm_id)
        cluster_name = resolve_cluster_name_for_vm(vm)

        try:
            job = create_and_enqueue_sync_job(
                cluster_name,
                request.user,
                "manual",
                details={
                    "vm_id": vm.pk,
                    "vm_name": vm.name,
                    "source": "vm_detail",
                },
            )
            messages.success(request, f"PVE sync for {vm.name} queued as background job #{job.id}.")
        except Exception as exc:
            messages.error(request, f"Unable to start sync for {vm.name}: {exc}")

        return redirect(request.POST.get("return_url") or vm.get_absolute_url())


# ============================================================================
# Webhook Receiver (function-based 鈥?needs @csrf_exempt)
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def webhook_receiver(request):
    """
    鎺ユ敹 PVE Webhook 浜嬩欢

    POST /api/plugins/pve-sync/webhook/

    Headers:
        X-PVE-Signature: <hmac_sha256_signature>

    Body (JSON):
    {
        "event": "vm-started",
        "node": "pve01",
        "vmid": 100,
        "vmname": "web01",
        "timestamp": "2025-03-30T15:30:00Z"
    }
    """
    try:
        raw_body = request.body.decode("utf-8")
        data = json.loads(raw_body)

        webhook_secret = get_plugin_config("webhook_secret")
        if webhook_secret:
            signature = request.headers.get("X-PVE-Signature", "")
            expected = hmac.new(
                webhook_secret.encode(), raw_body.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected):
                return JsonResponse(
                    {"status": "error", "message": "Invalid signature"}, status=403
                )

        event = PveWebhookEvent.objects.create(
            event_type=data.get("event", "unknown"),
            node=data.get("node"),
            vmid=data.get("vmid"),
            vm_name=data.get("vmname"),
            raw_data=data,
        )

        rq_job_id = enqueue_webhook_event(event)

        return JsonResponse(
            {
                "status": "success",
                "message": "Webhook received",
                "event_id": event.id,
                "rq_job_id": rq_job_id,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON"}, status=400
        )
    except Exception as e:
        return JsonResponse(
            {"status": "error", "message": str(e)}, status=500
        )
