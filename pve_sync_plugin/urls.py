"""
PVE Sync Plugin URLs — UI routes

Routes are mounted by NetBox under /plugins/pve-sync/
(the base_url from PluginConfig).
"""

from django.urls import include, path

from utilities.urls import get_model_urls

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
    path(
        "jobs/<int:pk>/",
        include(get_model_urls("pve_sync_plugin", "pvesyncjob")),
    ),

    # --- PveWebhookEvent CRUD ---
    path(
        "events/",
        views.PveWebhookEventListView.as_view(),
        name="pvewebhookevent_list",
    ),
    path(
        "events/<int:pk>/",
        include(get_model_urls("pve_sync_plugin", "pvewebhookevent")),
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
        include(get_model_urls("pve_sync_plugin", "pveclusterconfig")),
    ),

    # --- PveBackupStatus read-only ---
    path(
        "backup-status/",
        views.PveBackupStatusListView.as_view(),
        name="pvebackupstatus_list",
    ),
    path(
        "backup-status/<int:pk>/",
        include(get_model_urls("pve_sync_plugin", "pvebackupstatus")),
    ),

    # Webhook receiver (external, no auth, HMAC-verified)
    path("webhook/", views.webhook_receiver, name="webhook"),
]
