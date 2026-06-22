import logging

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
from dcim.models import Device
from virtualization.models import VirtualMachine

import json

logger = logging.getLogger(__name__)
import hmac
import hashlib

from netbox.context import current_request as _nb_current_request

from .filtersets import (
    PbsServerConfigFilterSet,
    PveBackupStatusFilterSet,
    PveClusterConfigFilterSet,
    PveDriftEventFilterSet,
    PveSyncJobFilterSet,
    PveWebhookEventFilterSet,
)
from .forms import (
    PbsServerConfigFilterForm,
    PbsServerConfigForm,
    PveClusterConfigFilterForm,
    PveClusterConfigForm,
    PveDriftEventFilterForm,
    PvePluginSettingsForm,
    PveSyncJobFilterForm,
    PveWebhookEventFilterForm,
)
from .models import (
    PbsServerConfig,
    PveBackupStatus,
    PveClusterConfig,
    PveDriftEvent,
    PvePluginSettings,
    PveSyncJob,
    PveWebhookEvent,
)
from .tables import (
    PbsServerConfigTable,
    PveBackupStatusTable,
    PveClusterConfigTable,
    PveDriftEventTable,
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
        clusters = PveClusterConfig.objects.filter(enabled=True).select_related("netbox_cluster", "netbox_site")
        pbs_servers = PbsServerConfig.objects.filter(enabled=True).select_related("netbox_site")

        # Collect all NetBox cluster IDs linked to enabled PVE configs
        nb_cluster_ids = [c.netbox_cluster_id for c in clusters if c.netbox_cluster_id]

        # Node stats (devices inside PVE clusters)
        node_qs = Device.objects.filter(cluster__id__in=nb_cluster_ids) if nb_cluster_ids else Device.objects.none()
        total_nodes = node_qs.count()
        online_nodes = node_qs.filter(status='active').count()
        offline_nodes = total_nodes - online_nodes

        # VM stats across all PVE clusters
        vm_qs = VirtualMachine.objects.filter(cluster__id__in=nb_cluster_ids) if nb_cluster_ids else VirtualMachine.objects.none()
        vm_stats = vm_qs.aggregate(
            total=Count("id"),
            running=Count("id", filter=Q(status="active")),
            stopped=Count("id", filter=Q(status="offline")),
            staged=Count("id", filter=Q(status="staged")),
        )

        # Per-cluster node & VM counts for the clusters table
        cluster_stats = {}
        if nb_cluster_ids:
            for row in Device.objects.filter(cluster__id__in=nb_cluster_ids).values("cluster_id").annotate(
                total=Count("id"), online=Count("id", filter=Q(status="active"))
            ):
                cluster_stats[row["cluster_id"]] = {"nodes": row["total"], "nodes_online": row["online"]}
            for row in VirtualMachine.objects.filter(cluster__id__in=nb_cluster_ids).values("cluster_id").annotate(
                total=Count("id"), running=Count("id", filter=Q(status="active"))
            ):
                cid = row["cluster_id"]
                cluster_stats.setdefault(cid, {})
                cluster_stats[cid]["vms"] = row["total"]
                cluster_stats[cid]["vms_running"] = row["running"]

        # Attach stats to each cluster object for easy template access
        for c in clusters:
            s = cluster_stats.get(c.netbox_cluster_id, {})
            c.stat_nodes = s.get("nodes", 0)
            c.stat_nodes_online = s.get("nodes_online", 0)
            c.stat_vms = s.get("vms", 0)
            c.stat_vms_running = s.get("vms_running", 0)

        # Alerts
        pending_webhooks = PveWebhookEvent.objects.filter(processed=False).count()
        backup_alerts = PveBackupStatus.objects.filter(
            last_backup__lt=timezone.now() - timezone.timedelta(days=7)
        ).count()
        offline_node_list = (
            node_qs.exclude(status="active")
            .select_related("cluster")
            .order_by("name")
        ) if nb_cluster_ids else Device.objects.none()

        # Recent jobs (last 10 only — full history has its own list page)
        recent_jobs = PveSyncJob.objects.order_by("-start_time")[:10]

        webhook_url = request.build_absolute_uri(reverse("plugins:pve_sync_plugin:webhook"))

        context = {
            "clusters": clusters,
            "pbs_servers": pbs_servers,
            "total_nodes": total_nodes,
            "online_nodes": online_nodes,
            "offline_nodes": offline_nodes,
            "total_vms": vm_stats["total"],
            "running_vms": vm_stats["running"],
            "stopped_vms": vm_stats["stopped"],
            "staged_vms": vm_stats["staged"],
            "pending_webhooks": pending_webhooks,
            "backup_alerts": backup_alerts,
            "offline_node_list": offline_node_list,
            "recent_jobs": recent_jobs,
            "webhook_url": webhook_url,
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
# PbsServerConfig Views
# ============================================================================

class PbsServerConfigListView(generic.ObjectListView):
    queryset = PbsServerConfig.objects.select_related("netbox_site")
    table = PbsServerConfigTable
    filterset = PbsServerConfigFilterSet
    filterset_form = PbsServerConfigFilterForm


class PbsServerConfigView(generic.ObjectView):
    queryset = PbsServerConfig.objects.all()
    template_name = "pve_sync/pbsserverconfig.html"


class PbsServerConfigEditView(generic.ObjectEditView):
    queryset = PbsServerConfig.objects.all()
    form = PbsServerConfigForm


class PbsServerConfigDeleteView(generic.ObjectDeleteView):
    queryset = PbsServerConfig.objects.all()


class PbsServerConfigBulkDeleteView(generic.BulkDeleteView):
    queryset = PbsServerConfig.objects.all()
    table = PbsServerConfigTable


class TriggerPbsSyncView(PermissionRequiredMixin, View):
    """Web GUI endpoint for manually triggering a PBS sync."""

    permission_required = "pve_sync_plugin.add_pvesyncjob"

    def post(self, request, pbs_pk):
        pbs = get_object_or_404(PbsServerConfig, pk=pbs_pk, enabled=True)
        cluster_name = f"pbs:{pbs.name}"

        if has_active_sync_job(cluster_name):
            messages.warning(request, f"PBS sync for {pbs.name} is already running.")
            return redirect(request.POST.get("return_url") or reverse("plugins:pve_sync_plugin:dashboard"))

        try:
            job = PveSyncJob.objects.create(
                cluster_name=cluster_name,
                status="pending",
                trigger="manual",
                triggered_by=request.user if request.user.is_authenticated else None,
                details={"pbs_server_id": pbs.pk, "pbs_server_name": pbs.name},
            )
            from .tasks import enqueue_pbs_sync
            enqueue_pbs_sync(job, pbs)
            messages.success(request, f"PBS sync for {pbs.name} queued as job #{job.id}.")
        except Exception as exc:
            messages.error(request, f"Unable to start PBS sync: {exc}")
        return redirect(
            request.POST.get("return_url") or reverse("plugins:pve_sync_plugin:dashboard")
        )


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
# PveDriftEvent
# ============================================================================

class PveDriftEventListView(generic.ObjectListView):
    queryset = PveDriftEvent.objects.select_related("sync_job")
    table = PveDriftEventTable
    filterset = PveDriftEventFilterSet
    filterset_form = PveDriftEventFilterForm


class PveDriftEventView(generic.ObjectView):
    queryset = PveDriftEvent.objects.select_related("sync_job")
    template_name = "pve_sync/pvedriftevent.html"


class PveDriftEventDeleteView(generic.ObjectDeleteView):
    queryset = PveDriftEvent.objects.all()


class PveDriftEventBulkDeleteView(generic.BulkDeleteView):
    queryset = PveDriftEvent.objects.all()
    table = PveDriftEventTable


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
            messages.success(request, "Proxmox Sync settings saved.")
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


class FullSyncView(PermissionRequiredMixin, View):
    """Clear state_db cache for a cluster and trigger a full resync."""

    permission_required = "pve_sync_plugin.add_pvesyncjob"

    def post(self, request, pk):
        from .models import PveClusterConfig, PvePluginSettings
        cluster = get_object_or_404(PveClusterConfig, pk=pk)

        if has_active_sync_job(cluster.name):
            messages.warning(request, f"Cluster '{cluster.name}' already has an active sync — please wait.")
            return redirect(cluster.get_absolute_url())

        try:
            settings = PvePluginSettings.load()
            db_path = settings.state_db_path or "/var/lib/pve-sync/state.db"
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            from state_db import StateDB
            cleared = StateDB(db_path).clear_cluster_cache(cluster.name)
            logger.info("Full sync: cleared %d state_db rows for cluster '%s'", cleared, cluster.name)
        except Exception as exc:
            logger.warning("Full sync: could not clear state_db: %s", exc)

        try:
            job = create_and_enqueue_sync_job(cluster.name, request.user, "manual",
                                              details={"source": "full_sync"})
            messages.success(request, f"Cache cleared — full sync queued as job #{job.id}.")
            return redirect(job.get_absolute_url())
        except Exception as exc:
            messages.error(request, f"Unable to start full sync: {exc}")
            return redirect(cluster.get_absolute_url())


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
# VM Provisioning Planner
# ============================================================================

class VmPlannerView(PermissionRequiredMixin, View):
    """Interactive VM provisioning planner: pick cluster/node/vmid, assign IPs, review checklist."""

    permission_required = "pve_sync_plugin.view_pveclusterconfig"

    def _context(self, request):
        from ipam.models import IPRange
        from .models import PveClusterConfig
        return {
            "clusters": PveClusterConfig.objects.order_by("name"),
            "ip_ranges": IPRange.objects.order_by("start_address"),
        }

    def get(self, request):
        return render(request, "pve_sync/vm_planner.html", self._context(request))

    def post(self, request):
        from ipam.models import IPRange, IPAddress
        import netaddr

        vm_name = request.POST.get("vm_name", "").strip()
        reserved = []
        errors = []

        for nic in ("management", "internet"):
            ip_str = request.POST.get(f"{nic}_ip", "").strip()
            range_id = request.POST.get(f"{nic}_ip_range", "").strip()
            if not ip_str or not range_id:
                continue
            try:
                ip_range = IPRange.objects.get(pk=range_id)
                prefix_len = ip_range.start_address.prefixlen
                cidr = f"{ip_str}/{prefix_len}"
                _, created = IPAddress.objects.get_or_create(
                    address=cidr,
                    defaults={
                        "status": "active",
                        "description": f"{vm_name} - {nic.capitalize()}",
                        "dns_name": vm_name.lower().replace(" ", "-") if vm_name else "",
                    },
                )
                if created:
                    reserved.append(f"{nic.capitalize()}: {cidr}")
                else:
                    errors.append(f"{nic.capitalize()} IP {ip_str} 已被使用")
            except IPRange.DoesNotExist:
                errors.append(f"找不到 IP Range (id={range_id})")
            except Exception as exc:
                errors.append(f"{nic.capitalize()}: {exc}")

        for msg in errors:
            messages.error(request, msg)
        if reserved:
            messages.success(request, "IP 已保留：" + "，".join(reserved))

        return render(request, "pve_sync/vm_planner.html", self._context(request))


class VmPlannerFreeIpsApi(PermissionRequiredMixin, View):
    """AJAX — return free IPs for an IP Range, optionally biased toward a preferred last octet."""

    permission_required = "pve_sync_plugin.view_pveclusterconfig"

    def get(self, request, range_id):
        from ipam.models import IPRange, IPAddress
        import netaddr

        try:
            ip_range = IPRange.objects.get(pk=range_id)
        except IPRange.DoesNotExist:
            return JsonResponse({"error": "Range not found"}, status=404)

        start_ip = ip_range.start_address.ip   # netaddr.IPAddress
        end_ip   = ip_range.end_address.ip
        prefix_len = ip_range.start_address.prefixlen

        # Fetch all IPAddresses once and filter in Python — avoids inet prefix
        # comparison issues with PostgreSQL __gte/__lte on mixed prefix-length values.
        used = set()
        for addr in IPAddress.objects.all().values_list("address", flat=True):
            h = addr.ip  # netaddr.IPAddress (host part)
            if start_ip <= h <= end_ip:
                used.add(str(h))

        # Build free list; keep up to 50 entries
        free = []
        for ip in netaddr.IPRange(str(start_ip), str(end_ip)):
            if str(ip) not in used:
                free.append({"ip": str(ip), "cidr": f"{ip}/{prefix_len}"})
            if len(free) >= 50:
                break

        # Preferred last octet — client sends ?prefer_last_octet=224 so we
        # can surface the same-octet IP first if it's free.
        prefer = request.GET.get("prefer_last_octet", "").strip()
        preferred = None
        if prefer.isdigit():
            octet = int(prefer)
            match = next((f for f in free if int(f["ip"].split(".")[-1]) == octet), None)
            if match:
                preferred = match

        return JsonResponse({
            "prefix_len": prefix_len,
            "range_display": f"{start_ip} – {end_ip}",
            "free_ips": free,
            "preferred": preferred,   # None if same-octet IP is already taken
        })


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

        # Suppress changelog: webhook is unauthenticated so current_request.user
        # would be AnonymousUser which ObjectChange.user rejects.
        _saved_request = _nb_current_request.get()
        _nb_current_request.set(None)
        try:
            event = PveWebhookEvent.objects.create(
                event_type=data.get("event", "unknown"),
                node=data.get("node"),
                vmid=data.get("vmid"),
                vm_name=data.get("vmname"),
                raw_data=data,
            )
        finally:
            _nb_current_request.set(_saved_request)

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
