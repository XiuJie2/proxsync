"""Check all PVE/PBS configs with a sync schedule and trigger overdue ones.

Also runs weekly state_db cleanup (retention: 90 days) — last-run time is
tracked in state_db so this command is the single source of truth for all
recurring maintenance; the only external trigger needed is a cron entry
calling this command every 15 minutes.
"""

import datetime
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

_SCHEDULE_INTERVALS = {
    "hourly":   datetime.timedelta(hours=1),
    "every_3h": datetime.timedelta(hours=3),
    "every_6h": datetime.timedelta(hours=6),
    "daily":    datetime.timedelta(hours=24),
    "weekly":   datetime.timedelta(weeks=1),
}

_CLEANUP_INTERVAL = datetime.timedelta(days=7)
_CLEANUP_RETAIN_DAYS = 90
_CLEANUP_STATE_KEY = "last_state_db_cleanup"


class Command(BaseCommand):
    help = (
        "Trigger scheduled PVE/PBS syncs and run weekly state_db cleanup. "
        "Intended to be called every 15 minutes via cron."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be triggered without actually enqueueing jobs or cleaning up.",
        )
        parser.add_argument(
            "--force-cleanup",
            action="store_true",
            help="Run state_db cleanup immediately regardless of the last-run time.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()
        triggered = 0

        triggered += self._check_pve_clusters(now, dry_run)
        triggered += self._check_pbs_servers(now, dry_run)

        self._maybe_cleanup_state_db(now, dry_run, force=options["force_cleanup"])

        level = self.style.SUCCESS if triggered else self.style.WARNING
        self.stdout.write(level(
            f"{'[dry-run] ' if dry_run else ''}Triggered {triggered} scheduled sync(s)."
        ))

    # ------------------------------------------------------------------
    # Sync scheduling
    # ------------------------------------------------------------------

    def _is_due(self, last_sync, schedule, now):
        interval = _SCHEDULE_INTERVALS.get(schedule)
        if not interval:
            return False
        if last_sync is None:
            return True
        return (now - last_sync) >= interval

    def _check_pve_clusters(self, now, dry_run):
        from pve_sync_plugin.models import PveClusterConfig, PveSyncJob
        from pve_sync_plugin.view_helpers import has_active_sync_job
        from pve_sync_plugin.tasks import enqueue_sync

        triggered = 0
        clusters = PveClusterConfig.objects.filter(enabled=True).exclude(sync_schedule="disabled")
        for cluster in clusters:
            if not self._is_due(cluster.last_sync, cluster.sync_schedule, now):
                logger.debug("PVE cluster '%s' not yet due (schedule=%s, last_sync=%s)",
                             cluster.name, cluster.sync_schedule, cluster.last_sync)
                continue

            if has_active_sync_job(cluster.name):
                self.stdout.write(f"  Skipping '{cluster.name}': sync already running.")
                continue

            self.stdout.write(f"  Triggering PVE sync for '{cluster.name}' (schedule={cluster.sync_schedule})")
            if not dry_run:
                job = PveSyncJob.objects.create(
                    cluster_name=cluster.name,
                    status="pending",
                    trigger="scheduled",
                    details={"source": "run_scheduled_syncs"},
                )
                enqueue_sync(job)
            triggered += 1

        return triggered

    def _check_pbs_servers(self, now, dry_run):
        from pve_sync_plugin.models import PbsServerConfig, PveSyncJob
        from pve_sync_plugin.tasks import enqueue_pbs_sync

        triggered = 0
        servers = PbsServerConfig.objects.filter(enabled=True).exclude(sync_schedule="disabled")
        for pbs in servers:
            if not self._is_due(pbs.last_sync, pbs.sync_schedule, now):
                logger.debug("PBS server '%s' not yet due (schedule=%s, last_sync=%s)",
                             pbs.name, pbs.sync_schedule, pbs.last_sync)
                continue

            active = PveSyncJob.objects.filter(
                cluster_name=f"pbs:{pbs.name}",
                status__in=["pending", "running"],
            ).exists()
            if active:
                self.stdout.write(f"  Skipping PBS '{pbs.name}': sync already running.")
                continue

            self.stdout.write(f"  Triggering PBS sync for '{pbs.name}' (schedule={pbs.sync_schedule})")
            if not dry_run:
                job = PveSyncJob.objects.create(
                    cluster_name=f"pbs:{pbs.name}",
                    status="pending",
                    trigger="scheduled",
                    details={"source": "run_scheduled_syncs", "pbs_server_pk": pbs.pk},
                )
                enqueue_pbs_sync(job, pbs)
            triggered += 1

        return triggered

    # ------------------------------------------------------------------
    # State DB cleanup
    # ------------------------------------------------------------------

    def _maybe_cleanup_state_db(self, now, dry_run, force=False):
        try:
            from state_db import StateDB
            from pve_sync_plugin.models import PvePluginSettings

            db_path = PvePluginSettings.load().state_db_path or "/var/lib/pve-sync/state.db"
            db = StateDB(db_path)

            last_run_str = db.get_state(_CLEANUP_STATE_KEY)
            last_run = None
            if last_run_str:
                try:
                    last_run = datetime.datetime.fromisoformat(last_run_str)
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=datetime.timezone.utc)
                except ValueError:
                    last_run = None

            due = force or last_run is None or (now - last_run) >= _CLEANUP_INTERVAL

            if not due:
                logger.debug(
                    "state_db cleanup not due yet (last=%s, interval=%s)",
                    last_run_str, _CLEANUP_INTERVAL,
                )
                return

            if dry_run:
                self.stdout.write(
                    f"  [dry-run] Would run state_db cleanup (retain {_CLEANUP_RETAIN_DAYS}d)."
                )
                return

            result = db.cleanup_old_data(_CLEANUP_RETAIN_DAYS)
            db.set_state(_CLEANUP_STATE_KEY, now.isoformat())

            total = sum(result.values())
            self.stdout.write(
                self.style.SUCCESS(
                    f"  state_db cleanup: removed {total} rows "
                    f"(vm_history={result['vm_config_history']} "
                    f"node_status={result['node_status_history']} "
                    f"node_resource={result['node_resource_history']} "
                    f"sync_log={result['sync_log']})"
                )
            )
            logger.info("state_db cleanup completed: %s", result)

        except Exception as exc:
            logger.warning("state_db cleanup failed (non-fatal): %s", exc)
