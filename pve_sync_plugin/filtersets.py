"""FilterSets for PVE Sync plugin models (used by list views and API)."""

import datetime

import django_filters
from django.db.models import Q
from django.utils import timezone

from netbox.filtersets import NetBoxModelFilterSet

from .choices import (
    BackupStatusChoices,
    DriftTypeChoices,
    SyncJobStatusChoices,
    SyncJobTriggerChoices,
    SyncScheduleChoices,
    VeeamResultChoices,
    VmTaskTypeChoices,
    WebhookEventChoices,
)
from .models import (
    PbsBackupStatus,
    PbsServerConfig,
    PveBackupStatus,
    PveClusterConfig,
    PveDriftEvent,
    PveSyncJob,
    PveVmTaskLog,
    PveWebhookEvent,
    VeeamBackupStatus,
    VeeamServerConfig,
)


class PveSyncJobFilterSet(NetBoxModelFilterSet):
    """Filter sync jobs by status, trigger, cluster, and time range."""

    status = django_filters.MultipleChoiceFilter(choices=SyncJobStatusChoices.choices)
    trigger = django_filters.MultipleChoiceFilter(choices=SyncJobTriggerChoices.choices)
    cluster_name = django_filters.CharFilter(lookup_expr="icontains")
    start_time_after = django_filters.DateTimeFilter(
        field_name="start_time", lookup_expr="gte"
    )
    start_time_before = django_filters.DateTimeFilter(
        field_name="start_time", lookup_expr="lte"
    )

    class Meta:
        model = PveSyncJob
        fields = ["id", "status", "trigger", "cluster_name"]

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(cluster_name__icontains=value)


class PveWebhookEventFilterSet(NetBoxModelFilterSet):
    """Filter webhook events by type, processing state, and VM."""

    event_type = django_filters.MultipleChoiceFilter(
        choices=WebhookEventChoices.choices
    )
    processed = django_filters.BooleanFilter()
    vmid = django_filters.NumberFilter()
    node = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = PveWebhookEvent
        fields = ["id", "event_type", "processed", "vmid", "node"]

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(vm_name__icontains=value)


class PveClusterConfigFilterSet(NetBoxModelFilterSet):
    """Filter cluster configs by name, enabled state, and schedule."""

    enabled = django_filters.BooleanFilter()
    sync_schedule = django_filters.MultipleChoiceFilter(
        choices=SyncScheduleChoices.choices
    )

    class Meta:
        model = PveClusterConfig
        fields = ["id", "name", "enabled", "sync_schedule"]

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(name__icontains=value) | queryset.filter(
            description__icontains=value
        )


class PbsServerConfigFilterSet(NetBoxModelFilterSet):
    """Filter PBS server configs by name and enabled state."""

    enabled = django_filters.BooleanFilter()

    class Meta:
        model = PbsServerConfig
        fields = ["id", "name", "enabled"]

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(name__icontains=value) | queryset.filter(
            description__icontains=value
        )


class PveDriftEventFilterSet(NetBoxModelFilterSet):
    """Filter drift events by type, VM name, cluster, and notification state."""

    drift_type = django_filters.MultipleChoiceFilter(choices=DriftTypeChoices.choices)
    vm_name = django_filters.CharFilter(lookup_expr="icontains")
    cluster_name = django_filters.CharFilter(lookup_expr="icontains")
    notified_telegram = django_filters.BooleanFilter()

    class Meta:
        model = PveDriftEvent
        fields = ["id", "drift_type", "vmid", "cluster_name", "notified_telegram"]

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(vm_name__icontains=value) | queryset.filter(cluster_name__icontains=value)


class PveVmTaskLogFilterSet(NetBoxModelFilterSet):
    """Filter VM task logs by type, operator, cluster, and VM."""

    task_type    = django_filters.MultipleChoiceFilter(choices=VmTaskTypeChoices.choices)
    vmid         = django_filters.NumberFilter()
    cluster_name = django_filters.CharFilter(lookup_expr="icontains")
    operator     = django_filters.CharFilter(lookup_expr="icontains")
    node         = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = PveVmTaskLog
        fields = ["id", "vmid", "task_type", "cluster_name", "operator", "node"]

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return (
            queryset.filter(vm_name__icontains=value)
            | queryset.filter(operator__icontains=value)
            | queryset.filter(cluster_name__icontains=value)
        )


class PveBackupStatusFilterSet(NetBoxModelFilterSet):
    """Filter backup statuses by state."""

    backup_status = django_filters.MultipleChoiceFilter(
        choices=BackupStatusChoices.choices
    )

    overdue = django_filters.BooleanFilter(method="filter_overdue")
    alerting = django_filters.BooleanFilter(method="filter_alerting")

    class Meta:
        model = PveBackupStatus
        fields = ["id", "backup_status"]

    def filter_overdue(self, queryset, name, value):
        """Backups older than the PBS threshold (VMs never backed up are not counted)."""
        overdue = _pbs_overdue_q()
        return queryset.filter(overdue) if value else queryset.exclude(overdue)

    def filter_alerting(self, queryset, name, value):
        """VMs that get a PBS backup-overdue alert (the Dashboard count)."""
        from .backup_alerts import pbs_alert_vms

        alerted = Q(vm__in=pbs_alert_vms().values("pk"))
        return queryset.filter(alerted) if value else queryset.exclude(alerted)

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(vm__name__icontains=value)


def _pbs_overdue_q():
    from .utils import get_threshold

    days = get_threshold("backup_overdue_days_pbs")
    if not days:
        return Q(pk__in=[])
    return Q(last_backup__lt=timezone.now() - datetime.timedelta(days=days))


class PbsBackupStatusFilterSet(NetBoxModelFilterSet):
    """Filter per-server PBS backups by server and staleness."""

    server_id = django_filters.ModelMultipleChoiceFilter(
        queryset=PbsServerConfig.objects.all(),
    )
    stale = django_filters.BooleanFilter(method="filter_stale")
    monitored = django_filters.BooleanFilter(method="filter_monitored")

    class Meta:
        model = PbsBackupStatus
        fields = ["id", "vm_id", "pve_backup_id"]

    def filter_stale(self, queryset, name, value):
        stale = _pbs_overdue_q() | Q(last_backup__isnull=True)
        return queryset.filter(stale) if value else queryset.exclude(stale)

    def filter_monitored(self, queryset, name, value):
        """VMs monitored for PBS backups (watch tag, not ignore tag, monitored cluster)."""
        from .backup_alerts import monitored_vms

        monitored = Q(vm__in=monitored_vms("pbs").values("pk"))
        return queryset.filter(monitored) if value else queryset.exclude(monitored)

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(vm__name__icontains=value) | Q(pve_backup_id__icontains=value))


class VeeamServerConfigFilterSet(NetBoxModelFilterSet):
    """Filter Veeam server configs by name and enabled state."""

    enabled = django_filters.BooleanFilter()

    class Meta:
        model = VeeamServerConfig
        fields = ["id", "name", "enabled"]

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(host__icontains=value) | Q(description__icontains=value)
        )


class VeeamBackupStatusFilterSet(NetBoxModelFilterSet):
    """Filter Veeam backup statuses by server, result and staleness."""

    server_id = django_filters.ModelMultipleChoiceFilter(
        queryset=VeeamServerConfig.objects.all(),
    )
    last_result = django_filters.MultipleChoiceFilter(choices=VeeamResultChoices.choices)
    stale = django_filters.BooleanFilter(method="filter_stale")
    problem = django_filters.BooleanFilter(method="filter_problem")
    alerting = django_filters.BooleanFilter(method="filter_alerting")

    class Meta:
        model = VeeamBackupStatus
        fields = ["id", "vm_id", "last_result", "job_name"]

    @staticmethod
    def _stale_q():
        from .backup_alerts import veeam_stale_q

        return veeam_stale_q()

    def filter_stale(self, queryset, name, value):
        stale = self._stale_q()
        return queryset.filter(stale) if value else queryset.exclude(stale)

    def filter_problem(self, queryset, name, value):
        problem = self._stale_q() | Q(last_result=VeeamResultChoices.FAILED)
        return queryset.filter(problem) if value else queryset.exclude(problem)

    def filter_alerting(self, queryset, name, value):
        """Rows that get a Veeam backup alert (the Dashboard count)."""
        from .backup_alerts import veeam_alert_statuses

        alerted = Q(pk__in=veeam_alert_statuses().values("pk"))
        return queryset.filter(alerted) if value else queryset.exclude(alerted)

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(vm__name__icontains=value) | Q(job_name__icontains=value))
