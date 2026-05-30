"""Background tasks for NetBox's RQ worker."""

import logging
import os
import tempfile

import yaml
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

        rq_job = django_rq.get_queue("default").enqueue(process_webhook_event, event.id)
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
        config_path = _write_runtime_config(job.cluster_name)

        from config import init_config
        import config as config_module

        config_module._global_config = None
        init_config(config_path)

        from sync import OptimizedPVEToNetBoxSync

        sync = OptimizedPVEToNetBoxSync()
        sync.sync()

        job.status = "success"
        job.end_time = timezone.now()
        job.total_vms = sync.stats.get("total_vms", 0)
        job.success_vms = sync.stats.get("success_vms", 0)
        job.failed_vms = max(job.total_vms - job.success_vms, 0)
        job.nodes_offline = sync.stats.get("nodes_offline", 0)
        job.config_drifts = sync.stats.get("config_drifts_detected", 0)
        job.tag_changes = sync.stats.get("tag_changes", 0)
        job.resource_alerts = sync.stats.get("resources_alert", 0)
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
    return {"status": "processed", "event_id": event.id, "sync_triggered": should_sync}


def _write_runtime_config(cluster_name):
    cluster = PveClusterConfig.objects.filter(name=cluster_name, enabled=True).first()

    if cluster:
        pve_host = cluster.pve_host
        pve_user = cluster.pve_user
        pve_token = cluster.pve_token
        pve_secret = cluster.pve_secret
        verify_ssl = cluster.pve_verify_ssl
        site_name = cluster.netbox_site.name if cluster.netbox_site else get_plugin_config("default_site", "Main Datacenter")
        cluster_type = (
            cluster.netbox_cluster_type.name
            if cluster.netbox_cluster_type
            else get_plugin_config("default_cluster_type", "Proxmox")
        )
        netbox_cluster = (
            cluster.netbox_cluster.name
            if cluster.netbox_cluster
            else get_plugin_config("default_netbox_cluster", "Proxmox Cluster")
        )
        logical_name = cluster.name
    else:
        pve_host = get_plugin_config("pve_api_host", "")
        pve_user = get_plugin_config("pve_api_user", "root@pam")
        pve_token = get_plugin_config("pve_api_token", "")
        pve_secret = get_plugin_config("pve_api_secret", "")
        verify_ssl = get_plugin_config("pve_api_verify_ssl", False)
        site_name = get_plugin_config("default_site", "Main Datacenter")
        cluster_type = get_plugin_config("default_cluster_type", "Proxmox")
        netbox_cluster = get_plugin_config("default_netbox_cluster", "Proxmox Cluster")
        logical_name = cluster_name

    config_data = {
        "clusters": [
            {
                "name": logical_name,
                "pve": {
                    "host": pve_host,
                    "user": pve_user,
                    "token": pve_token,
                    "secret": pve_secret,
                    "verify_ssl": bool(verify_ssl),
                },
                "netbox": {
                    "url": get_plugin_config("netbox_url", ""),
                    "token": get_plugin_config("netbox_token", ""),
                },
                "settings": {
                    "cluster_name": netbox_cluster,
                    "site_name": site_name,
                    "cluster_type": cluster_type,
                },
            }
        ],
        "telegram": {
            "enabled": bool(get_plugin_config("telegram_bot_token", "") and get_plugin_config("telegram_chat_id", "")),
            "bot_token": get_plugin_config("telegram_bot_token", ""),
            "chat_id": get_plugin_config("telegram_chat_id", ""),
        },
        "monitoring": {
            "node_offline_alert": True,
            "config_drift_alert": True,
            "tag_change_alert": True,
            "resource_alert": {
                "enabled": True,
                "memory_threshold": 85,
                "cpu_threshold": 90,
                "disk_threshold": 10,
            },
        },
        "sync": {
            "incremental": True,
            "force_full_sync": False,
            "batch_size": 50,
            "default_node_role": get_plugin_config("default_node_role", "PVE"),
            "default_node_type": get_plugin_config("default_node_type", "Standard Server"),
        },
        "state_db": {
            "path": get_plugin_config("state_db_path", "/tmp/pve-sync-state.db"),
            "cleanup_days": 90,
        },
    }

    config_file = tempfile.NamedTemporaryFile("w", prefix="pve-sync-", suffix=".yaml", delete=False)
    with config_file:
        yaml.safe_dump(config_data, config_file, allow_unicode=True, sort_keys=False)
    _apply_runtime_env(config_file.name, config_data)
    return config_file.name


def _apply_runtime_env(config_path, config_data):
    os.environ["PVE_SYNC_CONFIG_FILE"] = config_path
    cluster = config_data["clusters"][0]
    pve = cluster["pve"]
    netbox = cluster["netbox"]
    telegram = config_data.get("telegram", {})

    os.environ["PVE_API_HOST"] = str(pve.get("host", ""))
    os.environ["PVE_API_USER"] = str(pve.get("user", ""))
    os.environ["PVE_API_TOKEN"] = str(pve.get("token", ""))
    os.environ["PVE_API_SECRET"] = str(pve.get("secret", ""))
    os.environ["PVE_API_VERIFY_SSL"] = "true" if pve.get("verify_ssl") else "false"
    os.environ["NB_API_URL"] = str(netbox.get("url", ""))
    os.environ["NB_API_TOKEN"] = str(netbox.get("token", ""))
    os.environ["TELEGRAM_BOT_TOKEN"] = str(telegram.get("bot_token", ""))
    os.environ["TELEGRAM_CHAT_ID"] = str(telegram.get("chat_id", ""))


def _update_cluster_status(job):
    cluster = PveClusterConfig.objects.filter(name=job.cluster_name).first()
    if not cluster:
        return
    cluster.last_sync = job.end_time
    cluster.last_sync_status = job.status
    cluster.save(update_fields=["last_sync", "last_sync_status"])
