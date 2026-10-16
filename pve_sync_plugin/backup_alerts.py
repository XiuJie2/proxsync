"""Backup-overdue alerts. PBS and Veeam are checked independently: PBS covers
VMs with the watch tag (minus the ignore tag), Veeam every VM it backs up
(overdue days follow the job name, e.g. Everyday); neither looks at the other.

PBS alerts are sent after a PBS sync and Veeam alerts after a Veeam sync.
The Dashboard counts use the same queries, so the numbers it shows are the
VMs that actually get alerted.
"""

import datetime
import html
import logging
import time

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from .utils import VEEAM_JOB_PERIODS, get_plugin_config, get_threshold, send_backup_alert

logger = logging.getLogger(__name__)

# A VM is reminded at most once in this window, however many syncs run.
ALERT_INTERVAL = datetime.timedelta(hours=20)
# Telegram allows about 20 messages a minute in a group.
_SEND_GAP_SECONDS = 3
# Leading icon of each product's alerts, so PBS and Veeam can be told apart.
_PRODUCT_ICONS = {"PBS": "🟠", "Veeam": "🟢"}


def monitored_vms(kind=None):
    """VMs monitored for backups. PBS: VMs with the watch tag and without the
    ignore tag. Veeam: every VM (the tags are PBS-only). With ``kind`` ("pbs"
    or "veeam"), only VMs in the clusters chosen on that product's backup
    settings page (none chosen = all clusters)."""
    from virtualization.models import VirtualMachine

    from .models import PvePluginSettings

    qs = VirtualMachine.objects.all()
    if kind != "veeam":
        watch_tag = get_plugin_config("backup_watch_tag", "")
        if not watch_tag:
            return VirtualMachine.objects.none()
        qs = qs.filter(tags__name__iexact=watch_tag)
        ignore_tag = get_plugin_config("backup_ignore_tag", "")
        if ignore_tag:
            qs = qs.exclude(tags__name__iexact=ignore_tag)
    if kind:
        cluster_ids = list(
            getattr(PvePluginSettings.load(), f"backup_clusters_{kind}").values_list("pk", flat=True)
        )
        if cluster_ids:
            qs = qs.filter(cluster_id__in=cluster_ids)
    return qs.distinct()


def _cutoff(key):
    days = get_threshold(key)
    return (timezone.now() - datetime.timedelta(days=days)) if days else None


def pbs_alert_q(prefix=""):
    """Q (on VirtualMachine, or on a model reaching it via ``prefix``) for VMs
    whose PBS backup is overdue or which have never been backed up by PBS."""
    q = Q(**{f"{prefix}pve_backup_status__isnull": True}) | Q(
        **{f"{prefix}pve_backup_status__last_backup__isnull": True}
    )
    cutoff = _cutoff("backup_overdue_days_pbs")
    if cutoff:
        q |= Q(**{f"{prefix}pve_backup_status__last_backup__lt": cutoff})
    return q


def veeam_stale_q(prefix=""):
    """Q on VeeamBackupStatus (or a model reaching it via ``prefix``) for rows
    with no restore point or one older than the job's overdue days; the same
    test as VeeamBackupStatus.is_stale."""
    q = Q(**{f"{prefix}last_restore_point__isnull": True})
    default = get_threshold("backup_overdue_days_veeam")
    if not default:
        return q
    now = timezone.now()

    def older_than(days):
        # is_stale counts whole days, so "more than N days" starts at N + 1.
        return Q(**{f"{prefix}last_restore_point__lte": now - datetime.timedelta(days=days + 1)})

    unnamed = Q()
    for pattern, days in VEEAM_JOB_PERIODS:
        named = Q(**{f"{prefix}job_name__iregex": pattern})
        q |= named & older_than(days)
        unnamed &= ~named
    return q | (unnamed & older_than(default))


def veeam_alert_q(prefix=""):
    """Q on VeeamBackupStatus for rows that are alerted."""
    return veeam_stale_q(prefix) | Q(**{f"{prefix}last_result": "failed"})


def pbs_alert_vms():
    return monitored_vms("pbs").filter(pbs_alert_q()).select_related("cluster", "pve_backup_status")


def veeam_alert_statuses(server=None):
    from .models import VeeamBackupStatus

    qs = VeeamBackupStatus.objects.filter(vm__in=monitored_vms("veeam")).filter(veeam_alert_q())
    if server is not None:
        qs = qs.filter(server=server)
    return qs.select_related("vm", "vm__cluster", "server")


def pbs_alert_count():
    return pbs_alert_vms().count()


def veeam_alert_count():
    return veeam_alert_statuses().values("vm").distinct().count()


def _cluster_labels():
    """NetBox cluster pk -> the name of its PVE cluster config (as the old
    per-sync alerts showed it)."""
    from .models import PveClusterConfig

    return dict(PveClusterConfig.objects.values_list("netbox_cluster_id", "name"))


def _send_per_vm(kind, product, items):
    """Send one message per VM in ``items`` ([(vm, [problem, ...])]) that was not
    reminded within ALERT_INTERVAL. Returns the number of VMs reminded."""
    labels = _cluster_labels()
    # Only PBS monitoring is limited to VMs with the watch tag.
    watch_tag = get_plugin_config("backup_watch_tag", "") if product == "PBS" else ""
    sent = 0
    for vm, problems in items:
        key = f"pve_sync:backup_alert:{kind}:{vm.pk}"
        if cache.get(key):
            continue
        if sent:
            time.sleep(_SEND_GAP_SECONDS)
        cluster = labels.get(vm.cluster_id) or (vm.cluster.name if vm.cluster else "—")
        text = (
            f"{_PRODUCT_ICONS[product]} <b>{product} 備份逾期警告</b>\n\n"
            f"🖥️ 名稱: <b>{html.escape(vm.name)}</b> (ID: {html.escape(vm.serial or '?')})\n"
            f"🔀 叢集: {html.escape(cluster)}\n"
            f"📅 時間: {timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            + "\n".join(f"⏰ {html.escape(p)}" for p in problems)
            + (f"\n（標記 {html.escape(watch_tag)}，需定期備份）" if watch_tag else "")
            + f"\n⚠️ 請確認 {product} 備份任務是否正常執行。"
        )
        if send_backup_alert(text) is not True:
            continue
        cache.set(key, 1, int(ALERT_INTERVAL.total_seconds()))
        sent += 1
    return sent


def send_pbs_overdue_alerts():
    """Remind about monitored VMs with an overdue (or no) backup, one message
    per VM. Returns the number of VMs reminded."""
    items = []
    for vm in pbs_alert_vms().order_by("name"):
        status = getattr(vm, "pve_backup_status", None)
        if status is not None and status.last_backup:
            problem = f"PBS：已 {status.backup_age_days} 天未備份"
        else:
            problem = "PBS：從未有備份記錄"
        items.append((vm, [problem]))
    return _send_per_vm("pbs", "PBS", items)


def send_veeam_overdue_alerts(server):
    """Same as send_pbs_overdue_alerts, for the VMs backed up by ``server``."""
    items = []
    label = f"Veeam（{server.name}）"
    for status in veeam_alert_statuses(server).order_by("vm__name"):
        problems = []
        if status.last_restore_point is None:
            problems.append(f"{label}：沒有還原點")
        elif status.is_stale:
            problems.append(f"{label}：已 {status.backup_age_days} 天未備份")
        if status.last_result == "failed":
            reason = f"，{status.last_run_reason[:100]}" if status.last_run_reason else ""
            problems.append(f"{label}：最後一次備份失敗{reason}")
        if problems:
            items.append((status.vm, problems))
    return _send_per_vm(f"veeam{server.pk}", "Veeam", items)
