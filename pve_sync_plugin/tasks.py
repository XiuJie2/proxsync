"""Background tasks for NetBox's RQ worker."""

import datetime
import logging
import os
from datetime import timezone as dt_timezone

from django.utils import timezone

from .choices import BackupStatusChoices
from .models import PveClusterConfig, PveSyncJob, PveWebhookEvent
from .utils import get_plugin_config

logger = logging.getLogger(__name__)

# Maximum allowed runtime before a sync job is considered stale.
_JOB_TIMEOUT_MINUTES = 30
# RQ job timeout — must exceed the longest expected sync run.
_RQ_JOB_TIMEOUT = _JOB_TIMEOUT_MINUTES * 60  # 1800 seconds


def enqueue_sync(job):
    """Queue a sync job on NetBox's default RQ queue."""
    try:
        import django_rq

        rq_job = django_rq.get_queue("default").enqueue(
            run_sync_job, job.id, job_timeout=_RQ_JOB_TIMEOUT
        )
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


def _heartbeat_thread(job_id, stop_event):
    """Write a heartbeat to job.details every 30 s so the UI knows the worker is alive."""
    import threading
    from django.db import connection

    while not stop_event.wait(30):
        try:
            connection.close()  # Each iteration needs a fresh DB connection in this thread
            job = PveSyncJob.objects.get(pk=job_id)
            details = dict(job.details or {})
            details["heartbeat"] = timezone.now().isoformat()
            PveSyncJob.objects.filter(pk=job_id).update(details=details)
        except Exception:
            pass


def run_sync_job(job_id):
    """Run a PVE sync from a PveSyncJob record."""
    import threading

    job = PveSyncJob.objects.get(pk=job_id)
    job.status = "running"
    job.save(update_fields=["status"])
    config_path = None

    stop_hb = threading.Event()
    hb = threading.Thread(target=_heartbeat_thread, args=(job_id, stop_hb), daemon=True)
    hb.start()

    try:
        from .sync.config_bridge import cleanup_runtime_env, write_runtime_config_file
        from .sync.engine import PVESyncEngine

        config_path = write_runtime_config_file(job.cluster_name)

        engine = PVESyncEngine(config_path=config_path, job_id=job.id)
        stats = engine.run()

        job.refresh_from_db()
        job.status = "success"
        job.end_time = timezone.now()
        job.total_vms = stats.get("total_vms", 0)
        job.success_vms = stats.get("success_vms", 0)
        job.failed_vms = max(job.total_vms - job.success_vms, 0)
        job.nodes_offline = stats.get("nodes_offline", 0)
        job.config_drifts = stats.get("config_drifts_detected", 0)
        job.tag_changes = stats.get("tag_changes", 0)
        job.resource_alerts = stats.get("resources_alert", 0)
        job.details.pop("heartbeat", None)
        job.save()

        _update_cluster_status(job)
        logger.info("PVE sync job %s completed", job.id)
        return {"status": "success", "job_id": job.id}

    except Exception as exc:
        logger.exception("PVE sync job %s failed", job.id)
        job.refresh_from_db()
        job.status = "failed"
        job.end_time = timezone.now()
        job.details["error"] = str(exc)
        job.details.pop("heartbeat", None)
        job.save(update_fields=["status", "end_time", "details"])
        _update_cluster_status(job)
        return {"status": "failed", "job_id": job.id, "error": str(exc)}

    finally:
        stop_hb.set()

        if config_path:
            try:
                os.unlink(config_path)
            except OSError:
                pass

        try:
            from .sync.config_bridge import cleanup_runtime_env

            cleanup_runtime_env()
        except ImportError:
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


def cleanup_stale_jobs():
    """Mark jobs stuck in 'pending' or 'running' for too long as failed.

    This is intended to be called periodically (e.g. from a management
    command or housekeeping cron) to prevent orphaned jobs.
    """
    cutoff = timezone.now() - datetime.timedelta(minutes=_JOB_TIMEOUT_MINUTES)
    stale_jobs = PveSyncJob.objects.filter(
        status__in=["pending", "running"],
        start_time__lt=cutoff,
    )
    count = stale_jobs.update(
        status="failed",
        end_time=timezone.now(),
    )
    if count:
        logger.warning("Marked %d stale sync jobs as failed", count)
    return count


def _update_cluster_status(job):
    cluster = PveClusterConfig.objects.filter(name=job.cluster_name).first()
    if not cluster:
        return
    cluster.last_sync = job.end_time
    cluster.last_sync_status = job.status
    cluster.save(update_fields=["last_sync", "last_sync_status"])


# ---------------------------------------------------------------------------
# PBS sync
# ---------------------------------------------------------------------------

def enqueue_pbs_sync(job, pbs_server):
    """Queue a PBS sync job on NetBox's default RQ queue."""
    try:
        import django_rq

        rq_job = django_rq.get_queue("default").enqueue(
            run_pbs_sync_job, job.id, pbs_server.pk, job_timeout=_RQ_JOB_TIMEOUT
        )
        job.details["rq_job_id"] = rq_job.id
        job.save(update_fields=["details"])
        return rq_job.id
    except Exception as exc:
        job.status = "failed"
        job.end_time = timezone.now()
        job.details["queue_error"] = str(exc)
        job.save(update_fields=["status", "end_time", "details"])
        raise


def run_pbs_sync_job(job_id, pbs_server_pk):
    """Run a PBS sync from a PbsServerConfig record."""
    import threading
    from .models import PbsServerConfig

    job = PveSyncJob.objects.get(pk=job_id)
    pbs = PbsServerConfig.objects.get(pk=pbs_server_pk)
    job.status = "running"
    job.save(update_fields=["status"])

    stop_hb = threading.Event()
    hb = threading.Thread(target=_heartbeat_thread, args=(job_id, stop_hb), daemon=True)
    hb.start()

    try:
        import os

        # Set environment variables expected by the PBS sync script
        os.environ["PBS_HOST"] = pbs.pbs_host
        os.environ["PBS_TOKEN_NAME"] = pbs.pbs_token_name
        os.environ["PBS_TOKEN_SECRET"] = pbs.pbs_token_secret
        os.environ["PBS_VERIFY_SSL"] = "true" if pbs.pbs_verify_ssl else "false"
        os.environ["PBS_NODE_NAME"] = pbs.pbs_node_name
        os.environ["NB_API_URL"] = get_plugin_config("netbox_url", "")
        os.environ["NB_API_TOKEN"] = get_plugin_config("netbox_token", "")

        from pbs215_sync import PBSToNetBoxSync

        syncer = PBSToNetBoxSync()
        syncer.sync()

        # Write backup records to PveBackupStatus
        try:
            backup_records = _fetch_pbs_snapshots(pbs)
            updated, skipped = _apply_pbs_backup_status(backup_records)
            job.details["backup_updated"] = updated
            job.details["backup_skipped"] = skipped
            logger.info("PBS backup status: %d updated, %d no VM match", updated, skipped)
        except Exception as exc:
            logger.warning("PBS backup status sync failed (non-fatal): %s", exc)

        job.refresh_from_db()
        job.status = "success"
        job.end_time = timezone.now()
        job.details.pop("heartbeat", None)
        job.save()

        pbs.last_sync = job.end_time
        pbs.last_sync_status = "success"
        pbs.save(update_fields=["last_sync", "last_sync_status"])

        logger.info("PBS sync job %s completed for server %s", job.id, pbs.name)
        return {"status": "success", "job_id": job.id}

    except Exception as exc:
        logger.exception("PBS sync job %s failed for server %s", job.id, pbs.name)
        job.refresh_from_db()
        job.status = "failed"
        job.end_time = timezone.now()
        job.details["error"] = str(exc)
        job.details.pop("heartbeat", None)
        job.save(update_fields=["status", "end_time", "details"])

        pbs.last_sync = job.end_time
        pbs.last_sync_status = "failed"
        pbs.save(update_fields=["last_sync", "last_sync_status"])

        return {"status": "failed", "job_id": job.id, "error": str(exc)}

    finally:
        stop_hb.set()
        # Clean up PBS-specific env vars
        for key in ["PBS_HOST", "PBS_TOKEN_NAME", "PBS_TOKEN_SECRET",
                    "PBS_VERIFY_SSL", "PBS_NODE_NAME"]:
            os.environ.pop(key, None)


# ---------------------------------------------------------------------------
# PBS backup status helpers
# ---------------------------------------------------------------------------

def _fetch_pbs_snapshots(pbs):
    """Query PBS API and return the latest backup per vmid across all datastores.

    Returns:
        dict: {(backup_type, vmid_str): {'last_backup': datetime, 'size': int, 'pve_backup_id': str}}
    """
    import urllib3
    import requests

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    session = requests.Session()
    session.headers.update({
        "Authorization": f"PBSAPIToken={pbs.pbs_token_name}:{pbs.pbs_token_secret}",
        "Accept": "application/json",
    })
    host = pbs.pbs_host.rstrip("/")
    verify = pbs.pbs_verify_ssl

    # Get datastore list
    try:
        resp = session.get(f"{host}/api2/json/admin/datastore", verify=verify, timeout=15)
        datastores = resp.json().get("data", []) if resp.status_code == 200 else []
    except Exception as exc:
        logger.warning("PBS: cannot list datastores: %s", exc)
        return {}

    best = {}  # (type, vmid) -> best snapshot info

    for ds in datastores:
        store = ds.get("store") or ds.get("name")
        if not store:
            continue
        try:
            resp = session.get(
                f"{host}/api2/json/admin/datastore/{store}/snapshots",
                verify=verify, timeout=30,
            )
            if resp.status_code != 200:
                continue
            snapshots = resp.json().get("data", [])
        except Exception as exc:
            logger.warning("PBS: cannot list snapshots for %s: %s", store, exc)
            continue

        for snap in snapshots:
            btype = snap.get("backup-type", "vm")
            vmid = str(snap.get("backup-id", ""))
            if not vmid or btype not in ("vm", "ct"):
                continue

            ts = snap.get("backup-time", 0)
            backup_dt = (
                datetime.datetime.fromtimestamp(ts, tz=dt_timezone.utc) if ts else None
            )
            size = snap.get("size", 0) or 0

            key = (btype, vmid)
            existing = best.get(key)
            if existing is None or (backup_dt and backup_dt > existing["last_backup"]):
                best[key] = {
                    "last_backup": backup_dt,
                    "size": size,
                    "pve_backup_id": f"{btype}/{vmid}",
                    "backup_path": f"{store}/{btype}/{vmid}",
                }

    logger.info("PBS: found latest backups for %d VMs/CTs", len(best))
    return best


def _apply_pbs_backup_status(backup_records):
    """Write PBS backup data into PveBackupStatus Django model records.

    Matching priority:
      1. Existing PveBackupStatus where pve_backup_id already matches.
      2. VirtualMachine with custom_field_data__pve_vmid == vmid.

    Returns:
        (updated: int, skipped: int)
    """
    from .models import PveBackupStatus
    from virtualization.models import VirtualMachine

    updated = 0
    skipped = 0

    for (btype, vmid), info in backup_records.items():
        pve_backup_id = info["pve_backup_id"]
        last_backup = info.get("last_backup")
        size = info.get("size", 0)

        vm = None

        # 1. Find via existing pve_backup_id link
        existing = (
            PveBackupStatus.objects.filter(pve_backup_id=pve_backup_id)
            .select_related("vm")
            .first()
        )
        if existing:
            vm = existing.vm

        # 2. Find via custom field pve_vmid
        if vm is None:
            try:
                vm = VirtualMachine.objects.filter(
                    custom_field_data__vm_id=int(vmid)
                ).first()
            except Exception:
                pass

        if vm is None:
            skipped += 1
            logger.debug("PBS: no NetBox VM for %s/%s — skipping", btype, vmid)
            continue

        status_obj, _ = PveBackupStatus.objects.get_or_create(vm=vm)

        # Only update if this backup is newer than what is stored
        if last_backup and (status_obj.last_backup is None or last_backup > status_obj.last_backup):
            age_days = (timezone.now() - last_backup).days
            status_obj.last_backup = last_backup
            status_obj.backup_size = size if size else status_obj.backup_size
            status_obj.pve_backup_id = pve_backup_id
            status_obj.backup_path = info.get("backup_path", "")
            status_obj.backup_status = (
                BackupStatusChoices.STATUS_SUCCESS
                if age_days <= 7
                else BackupStatusChoices.STATUS_FAILED
            )
            status_obj.save(update_fields=[
                "last_backup", "backup_size", "pve_backup_id", "backup_path", "backup_status",
            ])
            updated += 1

    return updated, skipped
