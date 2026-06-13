from django.db import migrations, models
from django.utils import timezone

try:
    from utilities.json import CustomFieldJSONEncoder
except ModuleNotFoundError:
    CustomFieldJSONEncoder = None


class Migration(migrations.Migration):

    dependencies = [
        ("pve_sync_plugin", "0002_pvepluginsettings"),
    ]

    operations = [
        migrations.RenameField(
            model_name="pveclusterconfig",
            old_name="created_at",
            new_name="created",
        ),
        migrations.RenameField(
            model_name="pveclusterconfig",
            old_name="updated_at",
            new_name="last_updated",
        ),
        migrations.AddField(
            model_name="pvesyncjob",
            name="created",
            field=models.DateTimeField(default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="pvesyncjob",
            name="last_updated",
            field=models.DateTimeField(default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="pvewebhookevent",
            name="created",
            field=models.DateTimeField(default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="pvewebhookevent",
            name="last_updated",
            field=models.DateTimeField(default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="pvebackupstatus",
            name="created",
            field=models.DateTimeField(default=timezone.now),
            preserve_default=False,
        ),
        migrations.RenameField(
            model_name="pvebackupstatus",
            old_name="updated_at",
            new_name="last_updated",
        ),
        migrations.AddField(
            model_name="pvepluginsettings",
            name="created",
            field=models.DateTimeField(default=timezone.now),
            preserve_default=False,
        ),
        migrations.RenameField(
            model_name="pvepluginsettings",
            old_name="updated_at",
            new_name="last_updated",
        ),
        migrations.AlterField(
            model_name="pveclusterconfig",
            name="created",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AlterField(
            model_name="pveclusterconfig",
            name="last_updated",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AlterField(
            model_name="pvesyncjob",
            name="created",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AlterField(
            model_name="pvesyncjob",
            name="last_updated",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AlterField(
            model_name="pvewebhookevent",
            name="created",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AlterField(
            model_name="pvewebhookevent",
            name="last_updated",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AlterField(
            model_name="pvebackupstatus",
            name="created",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AlterField(
            model_name="pvebackupstatus",
            name="last_updated",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AlterField(
            model_name="pvepluginsettings",
            name="created",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AlterField(
            model_name="pvepluginsettings",
            name="last_updated",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name="pveclusterconfig",
            name="custom_field_data",
            field=models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder),
        ),
        migrations.AddField(
            model_name="pvesyncjob",
            name="custom_field_data",
            field=models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder),
        ),
        migrations.AddField(
            model_name="pvewebhookevent",
            name="custom_field_data",
            field=models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder),
        ),
        migrations.AddField(
            model_name="pvebackupstatus",
            name="custom_field_data",
            field=models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder),
        ),
        migrations.AddField(
            model_name="pvepluginsettings",
            name="custom_field_data",
            field=models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder),
        ),
    ]
