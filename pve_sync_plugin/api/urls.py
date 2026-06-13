"""NetBox REST API routes for the PVE Sync plugin.

Mounted by NetBox under /api/plugins/pve-sync/.
"""

from django.urls import path
from netbox.api.routers import NetBoxRouter

from pve_sync_plugin import views as plugin_views

from . import views as api_views

app_name = "pve_sync_plugin-api"

router = NetBoxRouter()
router.APIRootView.cls_name = "PveSyncPluginRootView"

router.register("jobs", api_views.PveSyncJobViewSet)
router.register("events", api_views.PveWebhookEventViewSet)
router.register("clusters", api_views.PveClusterConfigViewSet)
router.register("backup-status", api_views.PveBackupStatusViewSet)
router.register("settings", api_views.PvePluginSettingsViewSet)

urlpatterns = [
    path("webhook/", plugin_views.webhook_receiver, name="webhook"),
    *router.urls,
]
