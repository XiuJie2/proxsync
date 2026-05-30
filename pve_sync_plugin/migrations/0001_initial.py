# Generated for the PVE-NetBox Sync plugin.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("dcim", "__latest__"),
        ("virtualization", "__latest__"),
    ]

    operations = [
        migrations.CreateModel(
            name="PveClusterConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True)),
                ("pve_host", models.CharField(max_length=200)),
                ("pve_user", models.CharField(max_length=100)),
                ("pve_token", models.CharField(max_length=100)),
                ("pve_secret", models.CharField(max_length=200)),
                ("pve_verify_ssl", models.BooleanField(default=False)),
                ("enabled", models.BooleanField(default=True)),
                (
                    "sync_schedule",
                    models.CharField(
                        choices=[
                            ("disabled", "Disabled"),
                            ("hourly", "Hourly"),
                            ("every_6h", "Every 6 hours"),
                            ("daily", "Daily"),
                            ("weekly", "Weekly"),
                        ],
                        default="disabled",
                        max_length=20,
                    ),
                ),
                ("last_sync", models.DateTimeField(blank=True, null=True)),
                ("last_sync_status", models.CharField(blank=True, max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "netbox_cluster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pve_sync_config",
                        to="virtualization.cluster",
                    ),
                ),
                (
                    "netbox_cluster_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="virtualization.clustertype",
                    ),
                ),
                (
                    "netbox_site",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pve_clusters",
                        to="dcim.site",
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="PveSyncJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cluster_name", models.CharField(default="default", help_text="同步的集群名称", max_length=100)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                            ("partial", "Partial Success"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("start_time", models.DateTimeField(auto_now_add=True)),
                ("end_time", models.DateTimeField(blank=True, null=True)),
                ("total_vms", models.IntegerField(default=0)),
                ("success_vms", models.IntegerField(default=0)),
                ("failed_vms", models.IntegerField(default=0)),
                ("nodes_offline", models.IntegerField(default=0)),
                ("config_drifts", models.IntegerField(default=0)),
                ("tag_changes", models.IntegerField(default=0)),
                ("resource_alerts", models.IntegerField(default=0)),
                ("details", models.JSONField(blank=True, default=dict)),
                (
                    "trigger",
                    models.CharField(
                        choices=[
                            ("manual", "Manual"),
                            ("scheduled", "Scheduled"),
                            ("webhook", "Webhook"),
                            ("api", "API Call"),
                        ],
                        default="manual",
                        max_length=20,
                    ),
                ),
                (
                    "triggered_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pve_sync_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-start_time"]},
        ),
        migrations.CreateModel(
            name="PveBackupStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_backup", models.DateTimeField(blank=True, null=True)),
                ("backup_size", models.BigIntegerField(blank=True, help_text="字节", null=True)),
                (
                    "backup_status",
                    models.CharField(
                        choices=[
                            ("success", "Success"),
                            ("failed", "Failed"),
                            ("running", "Running"),
                            ("unknown", "Unknown"),
                        ],
                        default="unknown",
                        max_length=20,
                    ),
                ),
                ("backup_path", models.CharField(blank=True, max_length=500)),
                ("next_backup", models.DateTimeField(blank=True, null=True)),
                ("pve_backup_id", models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "vm",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pve_backup_status",
                        to="virtualization.virtualmachine",
                    ),
                ),
            ],
            options={
                "verbose_name": "PVE Backup Status",
                "verbose_name_plural": "PVE Backup Statuses",
            },
        ),
        migrations.CreateModel(
            name="PveWebhookEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("vm-started", "VM Started"),
                            ("vm-stopped", "VM Stopped"),
                            ("vm-migrated", "VM Migrated"),
                            ("node-online", "Node Online"),
                            ("node-offline", "Node Offline"),
                            ("backup-done", "Backup Completed"),
                            ("backup-failed", "Backup Failed"),
                            ("configuration-change", "Configuration Change"),
                        ],
                        max_length=50,
                    ),
                ),
                ("node", models.CharField(blank=True, max_length=100, null=True)),
                ("vmid", models.IntegerField(blank=True, null=True)),
                ("vm_name", models.CharField(blank=True, max_length=200, null=True)),
                ("raw_data", models.JSONField(default=dict)),
                ("processed", models.BooleanField(default=False)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("processing_error", models.TextField(blank=True)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                (
                    "sync_job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="webhook_events",
                        to="pve_sync_plugin.pvesyncjob",
                    ),
                ),
            ],
            options={"ordering": ["-received_at"]},
        ),
        migrations.AddIndex(
            model_name="pvesyncjob",
            index=models.Index(fields=["status", "start_time"], name="pve_sync_pv_status_1b8f8d_idx"),
        ),
        migrations.AddIndex(
            model_name="pvesyncjob",
            index=models.Index(fields=["cluster_name"], name="pve_sync_pv_cluster_c7bb8f_idx"),
        ),
        migrations.AddIndex(
            model_name="pvewebhookevent",
            index=models.Index(fields=["event_type", "processed"], name="pve_sync_pv_event_t_5a9362_idx"),
        ),
        migrations.AddIndex(
            model_name="pvewebhookevent",
            index=models.Index(fields=["vmid"], name="pve_sync_pv_vmid_90e5c1_idx"),
        ),
        migrations.AddIndex(
            model_name="pvewebhookevent",
            index=models.Index(fields=["received_at"], name="pve_sync_pv_receive_ce4cf2_idx"),
        ),
    ]
