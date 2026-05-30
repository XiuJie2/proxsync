# Generated for editable PVE Sync plugin settings.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pve_sync_plugin", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PvePluginSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pve_api_host", models.CharField(blank=True, max_length=200)),
                ("pve_api_user", models.CharField(default="root@pam", max_length=100)),
                ("pve_api_token", models.CharField(blank=True, max_length=100)),
                ("pve_api_secret", models.CharField(blank=True, max_length=200)),
                ("pve_api_verify_ssl", models.BooleanField(default=False)),
                ("netbox_url", models.URLField(blank=True)),
                ("netbox_token", models.CharField(blank=True, max_length=200)),
                ("telegram_bot_token", models.CharField(blank=True, max_length=200)),
                ("telegram_chat_id", models.CharField(blank=True, max_length=100)),
                ("webhook_secret", models.CharField(blank=True, max_length=200)),
                ("default_cluster_name", models.CharField(default="default", max_length=100)),
                ("default_netbox_cluster", models.CharField(default="Proxmox Cluster", max_length=100)),
                ("default_site", models.CharField(default="Main Datacenter", max_length=100)),
                ("default_cluster_type", models.CharField(default="Proxmox", max_length=100)),
                ("default_node_role", models.CharField(default="PVE", max_length=100)),
                ("default_node_type", models.CharField(default="Standard Server", max_length=100)),
                ("state_db_path", models.CharField(default="/var/lib/netbox/pve-sync-state.db", max_length=500)),
                ("enable_backup_sync", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "PVE Sync Settings",
                "verbose_name_plural": "PVE Sync Settings",
            },
        ),
    ]
