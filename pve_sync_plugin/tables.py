"""NetBox tables for PVE Sync plugin list views."""

import django_tables2 as tables

from netbox.tables import NetBoxTable, columns

from .models import (
    PveBackupStatus,
    PveClusterConfig,
    PveSyncJob,
    PveWebhookEvent,
)


# ---------------------------------------------------------------------------
# PveSyncJob
# ---------------------------------------------------------------------------

class PveSyncJobTable(NetBoxTable):
    """Table for sync job history with status badges and timing information."""

    id = tables.Column(linkify=True)
    cluster_name = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()
    trigger = columns.ChoiceFieldColumn()
    start_time = columns.DateTimeColumn()
    end_time = columns.DateTimeColumn()
    success_rate = tables.Column(
        accessor="success_rate",
        verbose_name="Success %",
        orderable=False,
    )
    triggered_by = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = PveSyncJob
        fields = (
            "pk",
            "id",
            "cluster_name",
            "status",
            "trigger",
            "start_time",
            "end_time",
            "total_vms",
            "success_vms",
            "failed_vms",
            "success_rate",
            "nodes_offline",
            "config_drifts",
            "resource_alerts",
            "triggered_by",
        )
        default_columns = (
            "id",
            "cluster_name",
            "status",
            "trigger",
            "start_time",
            "end_time",
            "total_vms",
            "success_rate",
        )


# ---------------------------------------------------------------------------
# PveWebhookEvent
# ---------------------------------------------------------------------------

class PveWebhookEventTable(NetBoxTable):
    """Table for webhook events received from PVE."""

    id = tables.Column(linkify=True)
    event_type = columns.ChoiceFieldColumn()
    node = tables.Column()
    vmid = tables.Column(verbose_name="VM ID")
    vm_name = tables.Column()
    processed = columns.BooleanColumn()
    received_at = columns.DateTimeColumn()
    sync_job = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = PveWebhookEvent
        fields = (
            "pk",
            "id",
            "event_type",
            "node",
            "vmid",
            "vm_name",
            "processed",
            "received_at",
            "sync_job",
        )
        default_columns = (
            "id",
            "event_type",
            "node",
            "vmid",
            "vm_name",
            "processed",
            "received_at",
        )


# ---------------------------------------------------------------------------
# PveClusterConfig
# ---------------------------------------------------------------------------

class PveClusterConfigTable(NetBoxTable):
    """Table for PVE cluster connection profiles."""

    name = tables.Column(linkify=True)
    pve_host = tables.Column()
    enabled = columns.BooleanColumn()
    sync_schedule = columns.ChoiceFieldColumn()
    netbox_site = tables.Column(linkify=True)
    netbox_cluster = tables.Column(linkify=True)
    last_sync = columns.DateTimeColumn()
    last_sync_status = tables.Column()

    class Meta(NetBoxTable.Meta):
        model = PveClusterConfig
        fields = (
            "pk",
            "name",
            "pve_host",
            "pve_user",
            "enabled",
            "sync_schedule",
            "netbox_site",
            "netbox_cluster",
            "last_sync",
            "last_sync_status",
        )
        default_columns = (
            "name",
            "pve_host",
            "enabled",
            "sync_schedule",
            "netbox_site",
            "netbox_cluster",
            "last_sync",
            "last_sync_status",
        )


# ---------------------------------------------------------------------------
# PveBackupStatus
# ---------------------------------------------------------------------------

class PveBackupStatusTable(NetBoxTable):
    """Table for per-VM backup tracking."""

    id = tables.Column(linkify=True)
    vm = tables.Column(linkify=True, verbose_name="Virtual Machine")
    backup_status = columns.ChoiceFieldColumn()
    last_backup = columns.DateTimeColumn()
    backup_age_days = tables.Column(
        accessor="backup_age_days",
        verbose_name="Age (days)",
        orderable=False,
    )
    next_backup = columns.DateTimeColumn()

    class Meta(NetBoxTable.Meta):
        model = PveBackupStatus
        fields = (
            "pk",
            "id",
            "vm",
            "backup_status",
            "last_backup",
            "backup_age_days",
            "backup_size",
            "next_backup",
        )
        default_columns = (
            "id",
            "vm",
            "backup_status",
            "last_backup",
            "backup_age_days",
        )
