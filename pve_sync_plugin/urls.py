"""
PVE Sync Plugin URLs — UI routes

Routes are mounted by NetBox under /plugins/pve-sync/
(the base_url from PluginConfig).
"""

from django.urls import path

from . import views

app_name = "pve_sync_plugin"

urlpatterns = [
    # Dashboard
    path("", views.DashboardView.as_view(), name="dashboard"),

    # Manual sync triggers
    path("trigger/", views.TriggerSyncView.as_view(), name="trigger-sync"),
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

    # Webhook receiver (external, no auth, HMAC-verified)
    path("webhook/", views.webhook_receiver, name="webhook"),
]
