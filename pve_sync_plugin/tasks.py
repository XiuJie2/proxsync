"""Background tasks for NetBox's RQ worker."""

import logging
import os

from django.utils import timezone

from .models import PveClusterConfig, PveSyncJob, PveWebhookEvent
from .utils import get_plugin_config

logger = logging.getLogger(__name__)


def enqueue_sync(job):
    """Queue a sync job on NetBox's default RQ queue."""
    try:
        import django_rq

        rq_job = django_rq.get_queue("default").enqueue(run_sync_job, job.id)
        job.details["rq_job_id"] = rq_job.id
        job.save(update_fields=["details"])
        return rq_job.id
    except Exception as exc:
        job.status = "failed"
        job.end_time = timezone.now()
        job.details["queue_error"] = str(exc)
        job.save(update_fields=["status", "end_time", "details"])
        raise


def enqueue_webhook_event(event):
    try:
        import django_rq

        rq_job = django_rq.get_queue("default").enqueue(
            process_webhook_event, event.id
        )
        return rq_job.id
    except Exception as exc:
        event.mark_processed(error=f"Queue error: {exc}")
        raise


def run_sync_job(job_id):
    """Run a PVE sync from a PveSyncJob record."""
    job = PveSyncJob.objects.get(pk=job_id)
    job.status = "running"
    job.save(update_fields=["status"])
    config_path = None

    try:
        from .sync.config_bridge import write_runtime_config_file
        from .sync.engine import PVESyncEngine

        config_path = write_runtime_config_file(job.cluster_name)

        engine = PVESyncEngine(config_path=config_path)
        stats = engine.run()

        job.status = "success"
        job.end_time = timezone.now()
        job.total_vms = stats.get("total_vms", 0)
        job.success_vms = stats.get("success_vms", 0)
        job.failed_vms = max(job.total_vms - job.success_vms, 0)
        job.nodes_offline = stats.get("nodes_offline", 0)
        job.config_drifts = stats.get("config_drifts_detected", 0)
        job.tag_changes = stats.get("tag_changes", 0)
        job.resource_alerts = stats.get("resources_alert", 0)
        job.save()

        _update_cluster_status(job)
        logger.info("PVE sync job %s completed", job.id)
        return {"status": "success", "job_id": job.id}

    except Exception as exc:
        logger.exception("PVE sync job %s failed", job.id)
        job.status = "failed"
        job.end_time = timezone.now()
        job.details["error"] = str(exc)
        job.save(update_fields=["status", "end_time", "details"])
        _update_cluster_status(job)
        return {"status": "failed", "job_id": job.id, "error": str(exc)}

    finally:
        if config_path:
            try:
                os.unlink(config_path)
            except OSError:
                pass


def process_webhook_event(event_id):
    event = PveWebhookEvent.objects.get(pk=event_id)
    if event.processed:
        return {"status": "skipped", "event_id": event.id}

    event_mapping = {
        "vm-started": True,
        "vm-stopped": True,
        "vm-migrated": True,
        "backup-done": True,
        "backup-failed": True,
        "configuration-change": True,
    }
    should_sync = event_mapping.get(event.event_type, False)
    sync_job = None

    if should_sync:
        sync_job = PveSyncJob.objects.create(
            cluster_name=get_plugin_config("default_cluster_name", "default"),
            status="pending",
            trigger="webhook",
            details={"webhook_event_id": event.id, "vmid": event.vmid},
        )
        enqueue_sync(sync_job)

    event.mark_processed(sync_job=sync_job)
    return {
        "status": "processed",
        "event_id": event.id,
        "sync_triggered": should_sync,
    }


def _update_cluster_status(job):
    cluster = PveClusterConfig.objects.filter(name=job.cluster_name).first()
    if not cluster:
        return
    cluster.last_sync = job.end_time
    cluster.last_sync_status = job.status
    cluster.save(update_fields=["last_sync", "last_sync_status"])
