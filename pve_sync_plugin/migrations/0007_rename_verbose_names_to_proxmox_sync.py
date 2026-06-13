from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pve_sync_plugin", "0006_pbsserverconfig_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="pvesyncjob",
            options={
                "ordering": ["-start_time"],
                "verbose_name": "Proxmox Sync Job",
                "verbose_name_plural": "Proxmox Sync Jobs",
            },
        ),
        migrations.AlterModelOptions(
            name="pvepluginsettings",
            options={
                "verbose_name": "Proxmox Sync Settings",
                "verbose_name_plural": "Proxmox Sync Settings",
            },
        ),
    ]
