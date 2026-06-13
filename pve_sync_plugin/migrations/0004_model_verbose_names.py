from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pve_sync_plugin", "0003_netboxmodel_timestamps"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="pveclusterconfig",
            options={
                "ordering": ["name"],
                "verbose_name": "PVE Cluster Config",
                "verbose_name_plural": "PVE Cluster Configs",
            },
        ),
        migrations.AlterModelOptions(
            name="pvesyncjob",
            options={
                "ordering": ["-start_time"],
                "verbose_name": "PVE Sync Job",
                "verbose_name_plural": "PVE Sync Jobs",
            },
        ),
        migrations.AlterModelOptions(
            name="pvewebhookevent",
            options={
                "ordering": ["-received_at"],
                "verbose_name": "PVE Webhook Event",
                "verbose_name_plural": "PVE Webhook Events",
            },
        ),
    ]
