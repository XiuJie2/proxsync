"""NetBox tables for PVE Sync plugin list views."""

import django_tables2 as tables

from netbox.tables import NetBoxTable, columns

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
    netbox_device = tables.Column(linkify=True, verbose_name="NetBox Device")
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
            "netbox_device",
            "last_sync",
            "last_sync_status",
        )
        default_columns = (
            "name",
            "pbs_host",
            "pbs_node_name",
            "enabled",
            "netbox_device",
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


class PbsBackupStatusTable(NetBoxTable):
    """Table for per-server PBS backup tracking."""

    id = tables.Column(linkify=True)
    vm = tables.Column(linkify=True, verbose_name="Virtual Machine")
    server = tables.Column(linkify=True, verbose_name="PBS Server")
    pve_backup_id = tables.Column(verbose_name="Backup Group")
    last_backup = columns.DateTimeColumn(verbose_name="Last Backup")
    backup_age_days = tables.Column(
        accessor="backup_age_days",
        verbose_name="Age (days)",
        orderable=False,
    )
    actions = columns.ActionsColumn(actions=("delete", "changelog"))

    class Meta(NetBoxTable.Meta):
        model = PbsBackupStatus
        fields = (
            "pk",
            "id",
            "vm",
            "server",
            "pve_backup_id",
            "backup_path",
            "last_backup",
            "backup_age_days",
            "backup_size",
        )
        default_columns = (
            "vm",
            "server",
            "pve_backup_id",
            "last_backup",
            "backup_age_days",
        )


# ---------------------------------------------------------------------------
# Veeam
# ---------------------------------------------------------------------------

class VeeamServerConfigTable(NetBoxTable):
    """Table for Veeam B&R server connection profiles."""

    name = tables.Column(linkify=True)
    host = tables.Column()
    netbox_object = tables.Column(
        accessor="netbox_object", linkify=True, orderable=False, verbose_name="NetBox Device / VM"
    )
    enabled = columns.BooleanColumn()
    sync_schedule = columns.ChoiceFieldColumn()
    last_sync = columns.DateTimeColumn()
    last_sync_status = tables.Column()
    actions = columns.ActionsColumn(actions=("edit", "delete", "changelog"))

    class Meta(NetBoxTable.Meta):
        model = VeeamServerConfig
        fields = (
            "pk",
            "name",
            "host",
            "winrm_port",
            "username",
            "netbox_object",
            "enabled",
            "sync_schedule",
            "last_sync",
            "last_sync_status",
        )
        default_columns = (
            "name",
            "host",
            "netbox_object",
            "enabled",
            "sync_schedule",
            "last_sync",
            "last_sync_status",
        )


class VeeamBackupStatusTable(NetBoxTable):
    """Table for per-VM Veeam backup tracking."""

    id = tables.Column(linkify=True)
    vm = tables.Column(linkify=True, verbose_name="Virtual Machine")
    server = tables.Column(linkify=True, verbose_name="Veeam Server")
    job_name = tables.Column(verbose_name="Job")
    last_result = columns.ChoiceFieldColumn(verbose_name="Last Result")
    last_run_start = columns.DateTimeColumn(verbose_name="Last Run")
    last_restore_point = columns.DateTimeColumn(verbose_name="Last Restore Point")
    backup_age_days = tables.Column(
        accessor="backup_age_days",
        verbose_name="Age (days)",
        orderable=False,
    )
    last_run_reason = tables.Column(verbose_name="Reason")
    actions = columns.ActionsColumn(actions=("delete", "changelog"))

    class Meta(NetBoxTable.Meta):
        model = VeeamBackupStatus
        fields = (
            "pk",
            "id",
            "vm",
            "server",
            "job_name",
            "last_result",
            "last_run_start",
            "last_run_end",
            "last_restore_point",
            "backup_age_days",
            "restore_point_type",
            "last_run_reason",
        )
        default_columns = (
            "vm",
            "server",
            "job_name",
            "last_result",
            "last_run_start",
            "last_restore_point",
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
    created_by    = tables.Column(verbose_name="創建人")
    actions       = columns.ActionsColumn(actions=("delete",))

    class Meta(NetBoxTable.Meta):
        model = VmProvisioningLog
        fields = ("pk", "vm_name", "vmid", "cluster_name", "node", "status",
                  "management_ip", "internet_ip", "created_by", "created")
        default_columns = ("vm_name", "vmid", "cluster_name", "node", "status",
                           "management_ip", "internet_ip", "created_by")


# ---------------------------------------------------------------------------
# PveVmTaskLog
# ---------------------------------------------------------------------------

class PveVmTaskLogTable(NetBoxTable):
    vm_name      = tables.Column(verbose_name="VM 名稱")
    vmid         = tables.Column(verbose_name="VM ID")
    cluster_name = tables.Column(verbose_name="叢集")
    node         = tables.Column(verbose_name="節點")
    task_type    = columns.ChoiceFieldColumn(verbose_name="操作類型")
    operator     = tables.Column(verbose_name="操作者")
    start_time   = columns.DateTimeColumn(verbose_name="時間")
    status       = tables.Column(verbose_name="結果")
    notified_telegram = columns.BooleanColumn(verbose_name="已通知")
    actions      = columns.ActionsColumn(actions=("delete",))

    class Meta(NetBoxTable.Meta):
        model = PveVmTaskLog
        fields = ("pk", "vm_name", "vmid", "cluster_name", "node",
                  "task_type", "operator", "start_time", "status", "notified_telegram")
        default_columns = ("vm_name", "vmid", "cluster_name", "node",
                           "task_type", "operator", "start_time", "status")
