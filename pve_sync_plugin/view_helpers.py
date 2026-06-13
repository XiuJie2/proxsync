from django.shortcuts import get_object_or_404

from .models import PveClusterConfig, PveSyncJob
from .tasks import enqueue_sync


def has_active_sync_job(cluster_name):
    return PveSyncJob.objects.filter(
        cluster_name=cluster_name,
        status__in=["pending", "running"],
    ).exists()


def create_and_enqueue_sync_job(cluster_name, user, trigger, details=None):
    if cluster_name != "default":
        get_object_or_404(PveClusterConfig, name=cluster_name, enabled=True)

    job = PveSyncJob.objects.create(
        cluster_name=cluster_name,
        status="pending",
        trigger=trigger,
        triggered_by=user if getattr(user, "is_authenticated", False) else None,
        details=details or {},
    )
    enqueue_sync(job)
    job.refresh_from_db()
    return job


def resolve_cluster_name_for_vm(vm):
    if getattr(vm, "cluster_id", None):
        cluster = PveClusterConfig.objects.filter(
            netbox_cluster_id=vm.cluster_id,
            enabled=True,
        ).first()
        if cluster:
            return cluster.name
    return "default"
