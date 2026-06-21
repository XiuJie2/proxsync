"""Check all PVE/PBS configs with a sync schedule and trigger overdue ones."""

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


class Command(BaseCommand):
    help = "Trigger syncs for PVE clusters and PBS servers that are past their scheduled interval."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would run without actually doing it.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()
        triggered = 0

        triggered += self._check_pve_clusters(now, dry_run)
        triggered += self._check_pbs_servers(now, dry_run)

        level = self.style.SUCCESS if triggered else self.style.WARNING
        self.stdout.write(level(
            f"{'[dry-run] ' if dry_run else ''}Triggered {triggered} scheduled sync(s)."
        ))

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
        from pve_sync_plugin.view_helpers import has_active_sync_job

        triggered = 0
        servers = PbsServerConfig.objects.filter(enabled=True).exclude(sync_schedule="disabled")
        for pbs in servers:
            if not self._is_due(pbs.last_sync, pbs.sync_schedule, now):
                logger.debug("PBS server '%s' not yet due (schedule=%s, last_sync=%s)",
                             pbs.name, pbs.sync_schedule, pbs.last_sync)
                continue

            if has_active_sync_job(f"pbs:{pbs.name}"):
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
