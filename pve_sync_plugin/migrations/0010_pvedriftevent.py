import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pve_sync_plugin', '0009_add_every_3h_schedule'),
    ]

    operations = [
        migrations.CreateModel(
            name='PveDriftEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=None)),
                ('vm_name', models.CharField(max_length=200)),
                ('vmid', models.IntegerField()),
                ('cluster_name', models.CharField(max_length=100)),
                ('drift_type', models.CharField(
                    choices=[
                        ('hardware', '硬體配置變更'),
                        ('migration', 'VM 遷移'),
                        ('ip_change', 'IP 位址變更'),
                        ('tag_change', '標籤變更'),
                    ],
                    max_length=30,
                )),
                ('field_name', models.CharField(max_length=100, verbose_name='欄位')),
                ('old_value', models.TextField(blank=True, verbose_name='舊值')),
                ('new_value', models.TextField(blank=True, verbose_name='新值')),
                ('notified_telegram', models.BooleanField(default=False)),
                ('sync_job', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='drift_events',
                    to='pve_sync_plugin.pvesyncjob',
                )),
            ],
            options={
                'verbose_name': 'VM Drift Event',
                'verbose_name_plural': 'VM Drift Events',
                'ordering': ['-created'],
            },
        ),
        migrations.AddIndex(
            model_name='pvedriftevent',
            index=models.Index(fields=['vmid', 'cluster_name'], name='pvesync_drift_vm_idx'),
        ),
        migrations.AddIndex(
            model_name='pvedriftevent',
            index=models.Index(fields=['drift_type'], name='pvesync_drift_type_idx'),
        ),
        migrations.AddIndex(
            model_name='pvedriftevent',
            index=models.Index(fields=['created'], name='pvesync_drift_created_idx'),
        ),
    ]
