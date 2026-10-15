import django.db.models.deletion
from django.db import migrations, models

import pve_sync_plugin.fields

class Migration(migrations.Migration):

    dependencies = [
        ('dcim', '__latest__'),
        ('virtualization', '__latest__'),
        ('pve_sync_plugin', '0021_veeam'),
    ]

    operations = [
        # Backup-monitoring thresholds
        migrations.AddField(
            model_name='pvepluginsettings',
            name='backup_overdue_days_pbs',
            field=models.PositiveIntegerField(default=7, help_text='PBS 超過幾天沒有新備份視為逾期（0 = 不檢查）'),
        ),
        migrations.AddField(
            model_name='pvepluginsettings',
            name='backup_overdue_days_veeam',
            field=models.PositiveIntegerField(default=7, help_text='Veeam 超過幾天沒有新還原點視為逾期（0 = 不檢查）'),
        ),
        migrations.AddField(
            model_name='pvepluginsettings',
            name='veeam_job_not_run_hours',
            field=models.PositiveIntegerField(default=26, help_text='已啟用的 Veeam 備份任務超過幾小時沒有執行就告警（0 = 不檢查）'),
        ),
        migrations.AddField(
            model_name='pvepluginsettings',
            name='veeam_repo_free_percent',
            field=models.PositiveIntegerField(default=10, help_text='Veeam Repository 剩餘空間低於幾 % 就告警（0 = 不檢查）'),
        ),
        migrations.AddField(
            model_name='pvepluginsettings',
            name='sync_failure_alert_count',
            field=models.PositiveIntegerField(default=2, help_text='PBS / Veeam 同步連續失敗幾次就告警（0 = 不告警）'),
        ),
        # Sync failure tracking
        migrations.AddField(
            model_name='pbsserverconfig',
            name='consecutive_failures',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='pbsserverconfig',
            name='failure_alerted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='veeamserverconfig',
            name='consecutive_failures',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='veeamserverconfig',
            name='failure_alerted',
            field=models.BooleanField(default=False),
        ),
        # Links to the NetBox objects of the backup servers
        migrations.AddField(
            model_name='pbsserverconfig',
            name='netbox_device',
            field=models.ForeignKey(blank=True, help_text='The NetBox device of this PBS host (found by node name when left empty)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pbs_server_configs', to='dcim.device'),
        ),
        migrations.AddField(
            model_name='veeamserverconfig',
            name='netbox_device',
            field=models.ForeignKey(blank=True, help_text='Physical NetBox device running Veeam (found by IP when left empty)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='veeam_server_configs', to='dcim.device'),
        ),
        migrations.AddField(
            model_name='veeamserverconfig',
            name='netbox_vm',
            field=models.ForeignKey(blank=True, help_text='NetBox virtual machine running Veeam (found by IP when left empty)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='veeam_server_configs', to='virtualization.virtualmachine'),
        ),
        # Encrypted credentials
        migrations.AlterField(
            model_name='pveclusterconfig',
            name='pve_secret',
            field=pve_sync_plugin.fields.EncryptedTextField(),
        ),
        migrations.AlterField(
            model_name='pbsserverconfig',
            name='pbs_token_secret',
            field=pve_sync_plugin.fields.EncryptedTextField(),
        ),
        migrations.AlterField(
            model_name='veeamserverconfig',
            name='password',
            field=pve_sync_plugin.fields.EncryptedTextField(),
        ),
    ]
