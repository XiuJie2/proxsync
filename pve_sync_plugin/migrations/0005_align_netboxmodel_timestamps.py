from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):
    dependencies = [
        ("pve_sync_plugin", "0004_model_verbose_names"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pvebackupstatus",
            name="created",
            field=models.DateTimeField(
                auto_now_add=True,
                blank=True,
                null=True,
                verbose_name=_("created"),
            ),
        ),
        migrations.AlterField(
            model_name="pvebackupstatus",
            name="last_updated",
            field=models.DateTimeField(
                auto_now=True,
                blank=True,
                null=True,
                verbose_name=_("last updated"),
            ),
        ),
        migrations.AlterField(
            model_name="pveclusterconfig",
            name="created",
            field=models.DateTimeField(
                auto_now_add=True,
                blank=True,
                null=True,
                verbose_name=_("created"),
            ),
        ),
        migrations.AlterField(
            model_name="pveclusterconfig",
            name="last_updated",
            field=models.DateTimeField(
                auto_now=True,
                blank=True,
                null=True,
                verbose_name=_("last updated"),
            ),
        ),
        migrations.AlterField(
            model_name="pvepluginsettings",
            name="created",
            field=models.DateTimeField(
                auto_now_add=True,
                blank=True,
                null=True,
                verbose_name=_("created"),
            ),
        ),
        migrations.AlterField(
            model_name="pvepluginsettings",
            name="last_updated",
            field=models.DateTimeField(
                auto_now=True,
                blank=True,
                null=True,
                verbose_name=_("last updated"),
            ),
        ),
        migrations.AlterField(
            model_name="pvesyncjob",
            name="created",
            field=models.DateTimeField(
                auto_now_add=True,
                blank=True,
                null=True,
                verbose_name=_("created"),
            ),
        ),
        migrations.AlterField(
            model_name="pvesyncjob",
            name="last_updated",
            field=models.DateTimeField(
                auto_now=True,
                blank=True,
                null=True,
                verbose_name=_("last updated"),
            ),
        ),
        migrations.AlterField(
            model_name="pvewebhookevent",
            name="created",
            field=models.DateTimeField(
                auto_now_add=True,
                blank=True,
                null=True,
                verbose_name=_("created"),
            ),
        ),
        migrations.AlterField(
            model_name="pvewebhookevent",
            name="last_updated",
            field=models.DateTimeField(
                auto_now=True,
                blank=True,
                null=True,
                verbose_name=_("last updated"),
            ),
        ),
    ]
