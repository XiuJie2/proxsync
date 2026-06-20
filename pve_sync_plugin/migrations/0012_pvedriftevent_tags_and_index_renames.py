import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0138_customfieldchoiceset_choice_colors'),
        ('pve_sync_plugin', '0011_pveclusterconfig_notify_on_sync'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='pvedriftevent',
            new_name='pve_sync_pl_vmid_64cef6_idx',
            old_name='pvesync_drift_vm_idx',
        ),
        migrations.RenameIndex(
            model_name='pvedriftevent',
            new_name='pve_sync_pl_drift_t_4c2f0c_idx',
            old_name='pvesync_drift_type_idx',
        ),
        migrations.RenameIndex(
            model_name='pvedriftevent',
            new_name='pve_sync_pl_created_5440dd_idx',
            old_name='pvesync_drift_created_idx',
        ),
        migrations.AddField(
            model_name='pvedriftevent',
            name='tags',
            field=taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag'),
        ),
        migrations.AlterField(
            model_name='pvedriftevent',
            name='custom_field_data',
            field=models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
        ),
    ]
