"""FilterSets for PVE Sync plugin models (used by list views and API)."""

import django_filters

from netbox.filtersets import NetBoxModelFilterSet

from .choices import (
    BackupStatusChoices,
    DriftTypeChoices,
    SyncJobStatusChoices,
    SyncJobTriggerChoices,
    SyncScheduleChoices,
    VmTaskTypeChoices,
    WebhookEventChoices,
)
from .models import (
    PbsServerConfig,
    PveBackupStatus,
    PveClusterConfig,
    PveDriftEvent,
    PveSyncJob,
    PveVmTaskLog,
    PveWebhookEvent,
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

    class Meta:
        model = PveBackupStatus
        fields = ["id", "backup_status"]

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(vm__name__icontains=value)
