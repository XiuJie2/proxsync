"""Queue a PVE-NetBox sync through the NetBox plugin job path."""

import json
import time
from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    """Headless equivalent of clicking Sync now in the plugin UI."""

    help = "Queue a PVE-NetBox sync using the plugin's PveSyncJob model and RQ worker."

    def add_arguments(self, parser: ArgumentParser):
        parser.add_argument(
            "--cluster",
            default="default",
            help="PVE cluster profile name to sync. Defaults to the plugin default profile.",
        )
        parser.add_argument(
            "--user",
            dest="username",
            default=None,
            help="Username to attribute the job to. Defaults to the oldest active superuser.",
        )
        parser.add_argument(
            "--wait",
            action="store_true",
            help="Wait for the queued job to finish and mirror its success/failure.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=7200,
            help="Maximum seconds to wait when --wait is set.",
        )
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=2.0,
            help="Seconds between status checks when --wait is set.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip duplicate-job check and force a new sync.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print resolved configuration (with secrets redacted) and exit without syncing.",
        )
        parser.add_argument(
            "--cleanup-stale",
            action="store_true",
            help="Mark stale jobs (>30 min in pending/running) as failed, then exit.",
        )

    def handle(self, *args, **options):
        from pve_sync_plugin.models import PveClusterConfig, PveSyncJob
        from pve_sync_plugin.tasks import cleanup_stale_jobs, enqueue_sync

        # --cleanup-stale: housekeeping mode
        if options["cleanup_stale"]:
            count = cleanup_stale_jobs()
            self.stdout.write(
                self.style.SUCCESS(f"Cleaned up {count} stale job(s).")
            )
            return

        cluster_name = options["cluster"]
        if cluster_name != "default":
            exists = PveClusterConfig.objects.filter(
                name=cluster_name,
                enabled=True,
            ).exists()
            if not exists:
                raise CommandError(f"Enabled PVE cluster profile '{cluster_name}' was not found.")

        # --dry-run: print config and exit
        if options["dry_run"]:
            self._handle_dry_run(cluster_name)
            return

        # Check for duplicate running jobs (unless --force)
        if not options["force"]:
            active = PveSyncJob.objects.filter(
                cluster_name=cluster_name,
                status__in=["pending", "running"],
            ).exists()
            if active:
                raise CommandError(
                    f"A sync job is already running for cluster '{cluster_name}'. "
                    f"Use --force to bypass this check."
                )

        user = self._resolve_user(options.get("username"))
        job = PveSyncJob.objects.create(
            cluster_name=cluster_name,
            status="pending",
            trigger="scheduled",
            triggered_by=user,
            details={"source": "management_command"},
        )

        try:
            rq_job_id = enqueue_sync(job)
        except Exception as exc:
            raise CommandError(f"Failed to enqueue PVE sync job: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Queued PVE sync job #{job.pk} for cluster '{cluster_name}'"
                f" on RQ job {rq_job_id}."
            )
        )

        if options["wait"]:
            self._wait_for_job(job.pk, options["timeout"], options["poll_interval"])

    def _handle_dry_run(self, cluster_name):
        """Print the resolved runtime config with secrets redacted."""
        from pve_sync_plugin.sync.config_bridge import build_runtime_config_from_db

        config = build_runtime_config_from_db(cluster_name)

        # Redact sensitive values
        for c in config.get("clusters", []):
            pve = c.get("pve", {})
            for secret_key in ("secret", "token"):
                if pve.get(secret_key):
                    pve[secret_key] = "***REDACTED***"
            nb = c.get("netbox", {})
            if nb.get("token"):
                nb["token"] = "***REDACTED***"
        tg = config.get("telegram", {})
        if tg.get("bot_token"):
            tg["bot_token"] = "***REDACTED***"

        self.stdout.write(json.dumps(config, indent=2, ensure_ascii=False))
        self.stdout.write(
            self.style.WARNING("\nDry run — no sync was executed.")
        )

    def _resolve_user(self, username):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        if username:
            user = user_model.objects.filter(username=username).first()
            if user is None:
                raise CommandError(f"User '{username}' does not exist.")
            return user

        return (
            user_model.objects.filter(is_active=True, is_superuser=True)
            .order_by("pk")
            .first()
        )

    def _wait_for_job(self, job_id, timeout, poll_interval):
        from pve_sync_plugin.models import PveSyncJob

        deadline = timezone.now().timestamp() + timeout
        while timezone.now().timestamp() < deadline:
            job = PveSyncJob.objects.get(pk=job_id)
            if job.status in {"success", "partial"}:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"PVE sync job #{job_id} finished: {job.status} — "
                        f"{job.success_vms}/{job.total_vms} VMs synced."
                    )
                )
                return
            if job.status == "failed":
                error = job.details.get("error") or job.details.get("queue_error") or "unknown error"
                raise CommandError(f"PVE sync job #{job_id} failed: {error}")
            time.sleep(poll_interval)

        raise CommandError(f"Timed out waiting for PVE sync job #{job_id}.")
