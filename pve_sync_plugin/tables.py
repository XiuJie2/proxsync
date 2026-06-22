"""NetBox tables for PVE Sync plugin list views."""

import django_tables2 as tables

from netbox.tables import NetBoxTable, columns

from .models import (
    PbsServerConfig,
    PveBackupStatus,
    PveClusterConfig,
    PveDriftEvent,
    PveSyncJob,
    PveWebhookEvent,
    VmProvisioningLog,
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
    actions = columns.ActionsColumn(actions=("delete", "changelog"))

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
    actions = columns.ActionsColumn(actions=("delete", "changelog"))

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
# PbsServerConfig
# ---------------------------------------------------------------------------

class PbsServerConfigTable(NetBoxTable):
    """Table for PBS server connection profiles."""

    name = tables.Column(linkify=True)
    pbs_host = tables.Column()
    pbs_node_name = tables.Column()
    enabled = columns.BooleanColumn()
    netbox_site = tables.Column(linkify=True)
    last_sync = columns.DateTimeColumn()
    last_sync_status = tables.Column()
    actions = columns.ActionsColumn(actions=("edit", "delete", "changelog"))

    class Meta(NetBoxTable.Meta):
        model = PbsServerConfig
        fields = (
            "pk",
            "name",
            "pbs_host",
            "pbs_node_name",
            "enabled",
            "netbox_site",
            "last_sync",
            "last_sync_status",
        )
        default_columns = (
            "name",
            "pbs_host",
            "pbs_node_name",
            "enabled",
            "netbox_site",
            "last_sync",
            "last_sync_status",
        )


# ---------------------------------------------------------------------------
# PveDriftEvent
# ---------------------------------------------------------------------------

class PveDriftEventTable(NetBoxTable):
    """Table for VM configuration drift events."""

    id = tables.Column(linkify=True)
    vm_name = tables.Column(verbose_name="VM 名稱")
    vmid = tables.Column(verbose_name="VM ID")
    cluster_name = tables.Column(verbose_name="叢集")
    drift_type = columns.ChoiceFieldColumn(verbose_name="變更類型")
    field_name = tables.Column(verbose_name="欄位")
    old_value = tables.Column(verbose_name="舊值")
    new_value = tables.Column(verbose_name="新值")
    notified_telegram = columns.BooleanColumn(verbose_name="已通知")
    created = columns.DateTimeColumn(verbose_name="偵測時間")
    sync_job = tables.Column(linkify=True, verbose_name="同步任務")
    actions = columns.ActionsColumn(actions=("delete",))

    class Meta(NetBoxTable.Meta):
        model = PveDriftEvent
        fields = (
            "pk",
            "id",
            "vm_name",
            "vmid",
            "cluster_name",
            "drift_type",
            "field_name",
            "old_value",
            "new_value",
            "notified_telegram",
            "created",
            "sync_job",
        )
        default_columns = (
            "id",
            "vm_name",
            "vmid",
            "cluster_name",
            "drift_type",
            "field_name",
            "old_value",
            "new_value",
            "notified_telegram",
            "created",
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
    actions = columns.ActionsColumn(actions=("changelog",))

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


# ---------------------------------------------------------------------------
# VmProvisioningLog
# ---------------------------------------------------------------------------

class VmProvisioningLogTable(NetBoxTable):
    vm_name       = tables.Column(linkify=True, verbose_name="VM 名稱")
    vmid          = tables.Column(verbose_name="VMID")
    cluster_name  = tables.Column(verbose_name="叢集")
    node          = tables.Column(verbose_name="節點")
    status        = columns.ChoiceFieldColumn(verbose_name="狀態")
    management_ip = tables.Column(verbose_name="Management IP")
    internet_ip   = tables.Column(verbose_name="Internet IP")
    actions       = columns.ActionsColumn(actions=("delete",))

    class Meta(NetBoxTable.Meta):
        model = VmProvisioningLog
        fields = ("pk", "vm_name", "vmid", "cluster_name", "node", "status",
                  "management_ip", "internet_ip", "created")
        default_columns = ("vm_name", "vmid", "cluster_name", "node", "status",
                           "management_ip", "internet_ip")
