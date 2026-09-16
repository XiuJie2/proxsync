from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pve_sync_plugin', '0016_pvevmtasklog_status_textfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='vmprovisioninglog',
            name='created_by',
            field=models.CharField(blank=True, max_length=150, verbose_name='創建人'),
        ),
    ]
