"""API ViewSets for PVE Sync plugin models."""

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status as drf_status

from netbox.api.viewsets import NetBoxModelViewSet

from pve_sync_plugin.filtersets import (
    PveBackupStatusFilterSet,
    PveClusterConfigFilterSet,
    PveSyncJobFilterSet,
    PveWebhookEventFilterSet,
)
from pve_sync_plugin.models import (
    PveBackupStatus,
    PveClusterConfig,
    PvePluginSettings,
    PveSyncJob,
    PveWebhookEvent,
    VmProvisioningLog,
)

from .serializers import (
    PveBackupStatusSerializer,
    PveClusterConfigSerializer,
    PvePluginSettingsSerializer,
    PveSyncJobSerializer,
    PveWebhookEventSerializer,
    VmProvisioningLogSerializer,
)


class PveSyncJobViewSet(NetBoxModelViewSet):
    queryset = PveSyncJob.objects.all()
    serializer_class = PveSyncJobSerializer
    filterset_class = PveSyncJobFilterSet

    @action(detail=False, methods=["post"], url_path="trigger")
    def trigger_sync(self, request):
        """POST /api/plugins/pve-sync/jobs/trigger/ — start a new sync."""
        from pve_sync_plugin.tasks import enqueue_sync

        cluster_name = request.data.get("cluster", "default")

        if cluster_name != "default":
            if not PveClusterConfig.objects.filter(
                name=cluster_name, enabled=True
            ).exists():
                return Response(
                    {"detail": f"Cluster '{cluster_name}' not found or disabled."},
                    status=drf_status.HTTP_404_NOT_FOUND,
                )

        job = PveSyncJob.objects.create(
            cluster_name=cluster_name,
            status="pending",
            trigger="api",
            triggered_by=request.user if request.user.is_authenticated else None,
            details={},
        )

        try:
            enqueue_sync(job)
        except Exception as exc:
            return Response(
                {"detail": f"Failed to enqueue: {exc}"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        job.refresh_from_db()
        serializer = self.get_serializer(job)
        return Response(serializer.data, status=drf_status.HTTP_202_ACCEPTED)


class PveWebhookEventViewSet(NetBoxModelViewSet):
    queryset = PveWebhookEvent.objects.all()
    serializer_class = PveWebhookEventSerializer
    filterset_class = PveWebhookEventFilterSet


class PveClusterConfigViewSet(NetBoxModelViewSet):
    queryset = PveClusterConfig.objects.all()
    serializer_class = PveClusterConfigSerializer
    filterset_class = PveClusterConfigFilterSet


class PveBackupStatusViewSet(NetBoxModelViewSet):
    queryset = PveBackupStatus.objects.select_related("vm")
    serializer_class = PveBackupStatusSerializer
    filterset_class = PveBackupStatusFilterSet


class PvePluginSettingsViewSet(NetBoxModelViewSet):
    queryset = PvePluginSettings.objects.all()
    serializer_class = PvePluginSettingsSerializer


class VmProvisioningLogViewSet(NetBoxModelViewSet):
    queryset = VmProvisioningLog.objects.order_by("-created")
    serializer_class = VmProvisioningLogSerializer
