import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0138_customfieldchoiceset_choice_colors'),
        ('virtualization', '__latest__'),
        ('pve_sync_plugin', '0023_encrypt_secrets_and_link_hosts'),
    ]

    operations = [
        migrations.CreateModel(
            name='PbsBackupStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('last_backup', models.DateTimeField(blank=True, null=True)),
                ('backup_size', models.BigIntegerField(blank=True, null=True)),
                ('backup_path', models.CharField(blank=True, max_length=500)),
                ('pve_backup_id', models.CharField(blank=True, max_length=100)),
                ('server', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='backup_statuses', to='pve_sync_plugin.pbsserverconfig')),
                ('vm', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pbs_backup_statuses', to='virtualization.virtualmachine')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'verbose_name': 'PBS Backup Status',
                'verbose_name_plural': 'PBS Backup Statuses',
                'ordering': ['vm__name'],
                'constraints': [models.UniqueConstraint(fields=('vm', 'server'), name='pbsbackupstatus_unique_vm_server')],
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
    ]
