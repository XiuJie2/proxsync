from django.db import migrations, models


def reassign_in_progress(apps, schema_editor):
    """The "部署中" status is being removed; fold any existing rows into 規劃中."""
    VmProvisioningLog = apps.get_model('pve_sync_plugin', 'VmProvisioningLog')
    VmProvisioningLog.objects.filter(status='in_progress').update(status='planning')


class Migration(migrations.Migration):

    dependencies = [
        ('pve_sync_plugin', '0017_vmprovisioninglog_created_by'),
    ]

    operations = [
        migrations.RunPython(reassign_in_progress, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='vmprovisioninglog',
            name='status',
            field=models.CharField(
                choices=[('planning', '規劃中'), ('completed', '完成')],
                default='planning', max_length=20, verbose_name='狀態',
            ),
        ),
    ]
