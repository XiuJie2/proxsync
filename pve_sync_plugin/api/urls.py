"""NetBox REST API routes.

These routes are mounted by NetBox under /api/plugins/pve-sync/.
"""

from django.urls import path

from pve_sync_plugin import views

app_name = "pve_sync_plugin"

urlpatterns = [
    path("trigger/", views.trigger_sync, name="trigger"),
    path("status/<int:job_id>/", views.sync_status, name="status"),
    path("jobs/", views.list_sync_jobs, name="jobs"),
    path("backup-status/", views.backup_status_list, name="backup-list"),
    path("backup-status/<int:vm_id>/", views.update_backup_status, name="backup-update"),
]
