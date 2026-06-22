"""
PVE Sync Plugin URLs — UI routes

Routes are mounted by NetBox under /plugins/pve-sync/
(the base_url from PluginConfig).
"""

from django.urls import path

from netbox.views.generic import ObjectChangeLogView

from . import views
from .models import PbsServerConfig, PveBackupStatus, PveClusterConfig, PveDriftEvent, PveSyncJob, PveVmTaskLog, PveWebhookEvent, VmProvisioningLog

app_name = "pve_sync_plugin"

urlpatterns = [
    # Dashboard
    path("", views.DashboardView.as_view(), name="dashboard"),

    # Manual sync triggers
    path("trigger/", views.TriggerSyncView.as_view(), name="trigger-sync"),
    path(
        "clusters/<int:pk>/full-sync/",
        views.FullSyncView.as_view(),
        name="cluster-full-sync",
    ),
    path(
        "virtual-machines/<int:vm_id>/sync/",
        views.TriggerVmSyncView.as_view(),
        name="trigger-vm-sync",
    ),

    # Plugin settings (singleton)
    path("settings/", views.PvePluginSettingsView.as_view(), name="settings"),

    # --- PveSyncJob CRUD ---
    path("jobs/", views.PveSyncJobListView.as_view(), name="pvesyncjob_list"),
    path("jobs/<int:pk>/", views.PveSyncJobView.as_view(), name="pvesyncjob"),
    path(
        "jobs/<int:pk>/delete/",
        views.PveSyncJobDeleteView.as_view(),
        name="pvesyncjob_delete",
    ),
    path(
        "jobs/delete/",
        views.PveSyncJobBulkDeleteView.as_view(),
        name="pvesyncjob_bulk_delete",
    ),
    path(
        "jobs/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="pvesyncjob_changelog",
        kwargs={"model": PveSyncJob},
    ),

    # --- PveWebhookEvent CRUD ---
    path(
        "events/",
        views.PveWebhookEventListView.as_view(),
        name="pvewebhookevent_list",
    ),
    path(
        "events/<int:pk>/",
        views.PveWebhookEventView.as_view(),
        name="pvewebhookevent",
    ),
    path(
        "events/<int:pk>/delete/",
        views.PveWebhookEventDeleteView.as_view(),
        name="pvewebhookevent_delete",
    ),
    path(
        "events/delete/",
        views.PveWebhookEventBulkDeleteView.as_view(),
        name="pvewebhookevent_bulk_delete",
    ),
    path(
        "events/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="pvewebhookevent_changelog",
        kwargs={"model": PveWebhookEvent},
    ),

    # --- PveClusterConfig CRUD ---
    path(
        "clusters/",
        views.PveClusterConfigListView.as_view(),
        name="pveclusterconfig_list",
    ),
    path(
        "clusters/add/",
        views.PveClusterConfigEditView.as_view(),
        name="pveclusterconfig_add",
    ),
    path(
        "clusters/<int:pk>/",
        views.PveClusterConfigView.as_view(),
        name="pveclusterconfig",
    ),
    path(
        "clusters/<int:pk>/edit/",
        views.PveClusterConfigEditView.as_view(),
        name="pveclusterconfig_edit",
    ),
    path(
        "clusters/<int:pk>/delete/",
        views.PveClusterConfigDeleteView.as_view(),
        name="pveclusterconfig_delete",
    ),
    path(
        "clusters/delete/",
        views.PveClusterConfigBulkDeleteView.as_view(),
        name="pveclusterconfig_bulk_delete",
    ),
    path(
        "clusters/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="pveclusterconfig_changelog",
        kwargs={"model": PveClusterConfig},
    ),

    # --- PveBackupStatus read-only ---
    path(
        "backup-status/",
        views.PveBackupStatusListView.as_view(),
        name="pvebackupstatus_list",
    ),
    path(
        "backup-status/<int:pk>/",
        views.PveBackupStatusView.as_view(),
        name="pvebackupstatus",
    ),
    path(
        "backup-status/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="pvebackupstatus_changelog",
        kwargs={"model": PveBackupStatus},
    ),

    # --- PbsServerConfig CRUD ---
    path("pbs/", views.PbsServerConfigListView.as_view(), name="pbsserverconfig_list"),
    path("pbs/add/", views.PbsServerConfigEditView.as_view(), name="pbsserverconfig_add"),
    path("pbs/<int:pk>/", views.PbsServerConfigView.as_view(), name="pbsserverconfig"),
    path(
        "pbs/<int:pk>/edit/",
        views.PbsServerConfigEditView.as_view(),
        name="pbsserverconfig_edit",
    ),
    path(
        "pbs/<int:pk>/delete/",
        views.PbsServerConfigDeleteView.as_view(),
        name="pbsserverconfig_delete",
    ),
    path(
        "pbs/delete/",
        views.PbsServerConfigBulkDeleteView.as_view(),
        name="pbsserverconfig_bulk_delete",
    ),
    path(
        "pbs/<int:pbs_pk>/sync/",
        views.TriggerPbsSyncView.as_view(),
        name="trigger-pbs-sync",
    ),
    path(
        "pbs/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="pbsserverconfig_changelog",
        kwargs={"model": PbsServerConfig},
    ),

    # --- PveDriftEvent ---
    path("drift/", views.PveDriftEventListView.as_view(), name="pvedriftevent_list"),
    path("drift/<int:pk>/", views.PveDriftEventView.as_view(), name="pvedriftevent"),
    path("drift/<int:pk>/delete/", views.PveDriftEventDeleteView.as_view(), name="pvedriftevent_delete"),
    path("drift/delete/", views.PveDriftEventBulkDeleteView.as_view(), name="pvedriftevent_bulk_delete"),
    path(
        "drift/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="pvedriftevent_changelog",
        kwargs={"model": PveDriftEvent},
    ),

    # --- PveVmTaskLog ---
    path("task-logs/", views.PveVmTaskLogListView.as_view(), name="pvevmtasklog_list"),
    path("task-logs/<int:pk>/delete/", views.PveVmTaskLogDeleteView.as_view(), name="pvevmtasklog_delete"),
    path("task-logs/delete/", views.PveVmTaskLogBulkDeleteView.as_view(), name="pvevmtasklog_bulk_delete"),
    path("task-logs/<int:pk>/changelog/", ObjectChangeLogView.as_view(),
         name="pvevmtasklog_changelog", kwargs={"model": PveVmTaskLog}),

    # IP probe APIs (used by provisioning form)
    path("provisioning/free-ips/<int:range_id>/", views.VmPlannerFreeIpsApi.as_view(), name="vm-planner-free-ips"),
    path("provisioning/check-ip/", views.VmPlannerCheckIpApi.as_view(), name="vm-planner-check-ip"),

    # VM Provisioning — combined planner + list
    path("provisioning/", views.VmProvisioningCombinedView.as_view(), name="vmprovisioninglog_list"),
    path("provisioning/<int:pk>/", views.VmProvisioningLogView.as_view(), name="vmprovisioninglog"),
    path("provisioning/<int:pk>/delete/", views.VmProvisioningLogDeleteView.as_view(), name="vmprovisioninglog_delete"),
    path("provisioning/<int:pk>/changelog/", ObjectChangeLogView.as_view(),
         name="vmprovisioninglog_changelog", kwargs={"model": VmProvisioningLog}),

    # Webhook receiver (external, no auth, HMAC-verified)
    path("webhook/", views.webhook_receiver, name="webhook"),
]
