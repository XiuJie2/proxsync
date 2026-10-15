import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0138_customfieldchoiceset_choice_colors'),
        ('pve_sync_plugin', '0020_pluginsettings_backup_tags'),
    ]

    operations = [
        migrations.CreateModel(
            name='VeeamServerConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
                ('host', models.CharField(help_text='Veeam B&R server hostname or IP', max_length=200)),
                ('winrm_port', models.PositiveIntegerField(default=5985)),
                ('winrm_use_https', models.BooleanField(default=False, help_text='Use WinRM over HTTPS (usually port 5986)')),
                ('winrm_verify_ssl', models.BooleanField(default=False)),
                ('username', models.CharField(help_text='Windows account allowed to log on over WinRM (e.g. Administrator or DOMAIN\\user)', max_length=150)),
                ('password', models.CharField(max_length=200)),
                ('enabled', models.BooleanField(default=True)),
                ('sync_schedule', models.CharField(default='disabled', max_length=20)),
                ('last_sync', models.DateTimeField(blank=True, null=True)),
                ('last_sync_status', models.CharField(blank=True, max_length=20)),
                ('server_info', models.JSONField(blank=True, default=dict)),
                ('job_summary', models.JSONField(blank=True, default=list, help_text='Last session of every backup job, as of the last sync')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'verbose_name': 'Veeam Server Config',
                'verbose_name_plural': 'Veeam Server Configs',
                'ordering': ['name'],
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.CreateModel(
            name='VeeamBackupStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('job_name', models.CharField(blank=True, max_length=200)),
                ('last_result', models.CharField(default='unknown', help_text="Result of this VM in the job's last session", max_length=20)),
                ('last_run_start', models.DateTimeField(blank=True, null=True)),
                ('last_run_end', models.DateTimeField(blank=True, null=True)),
                ('last_run_reason', models.TextField(blank=True)),
                ('last_restore_point', models.DateTimeField(blank=True, null=True)),
                ('restore_point_type', models.CharField(blank=True, max_length=50)),
                ('restore_point_consistent', models.BooleanField(blank=True, null=True)),
                ('veeam_object_id', models.CharField(blank=True, max_length=100)),
                ('server', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='backup_statuses', to='pve_sync_plugin.veeamserverconfig')),
                ('vm', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='veeam_backup_statuses', to='virtualization.virtualmachine')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'verbose_name': 'Veeam Backup Status',
                'verbose_name_plural': 'Veeam Backup Statuses',
                'ordering': ['vm__name'],
                'constraints': [models.UniqueConstraint(fields=('vm', 'server'), name='veeambackupstatus_unique_vm_server')],
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
    ]
