import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import PveClusterConfig, PveSyncJob
from .tasks import enqueue_sync

logger = logging.getLogger(__name__)


def has_active_sync_job(cluster_name):
    # Reconcile any RQ-failed jobs before checking for active ones, so a
    # worker restart doesn't permanently block future syncs.
    _reconcile_rq_status(cluster_name)
    from .tasks import cleanup_stale_jobs
    cleanup_stale_jobs()

    return PveSyncJob.objects.filter(
        cluster_name=cluster_name,
        status__in=["pending", "running"],
    ).exists()


def _reconcile_rq_status(cluster_name):
    """Mark DB jobs as failed when their RQ counterpart has already failed/disappeared."""
    active_jobs = PveSyncJob.objects.filter(
        cluster_name=cluster_name,
        status__in=["pending", "running"],
    )
    if not active_jobs.exists():
        return

    try:
        import django_rq
        from rq.job import Job, JobStatus

        q = django_rq.get_queue("default")
        terminal = {JobStatus.FAILED, JobStatus.CANCELED}

        for job in active_jobs:
            rq_job_id = job.details.get("rq_job_id")
            if not rq_job_id:
                continue
            try:
                rq_job = Job.fetch(rq_job_id, connection=q.connection)
                if rq_job.get_status() in terminal:
                    exc_info = getattr(rq_job, "exc_info", None) or ""
                    job.status = "failed"
                    job.end_time = timezone.now()
                    job.details["error"] = f"RQ job {rq_job_id} failed: {str(exc_info)[:200]}"
                    job.save(update_fields=["status", "end_time", "details"])
                    logger.warning("Reconciled RQ-failed job #%s for cluster %s", job.id, cluster_name)
            except Exception:
                # Job not found in Redis (expired / worker crashed).
                # If stuck >5 min, mark failed immediately instead of waiting 30 min.
                stuck_seconds = (timezone.now() - job.start_time).total_seconds()
                if stuck_seconds > 300:
                    job.status = "failed"
                    job.end_time = timezone.now()
                    job.details["error"] = (
                        f"RQ job {rq_job_id} not found in Redis after {int(stuck_seconds)}s "
                        "(worker crash or Redis flush?)"
                    )
                    job.save(update_fields=["status", "end_time", "details"])
                    logger.warning(
                        "Reconciled missing-RQ job #%s for cluster %s (stuck %ds)",
                        job.id, cluster_name, stuck_seconds,
                    )
    except Exception as exc:
        logger.debug("RQ reconcile skipped: %s", exc)


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
