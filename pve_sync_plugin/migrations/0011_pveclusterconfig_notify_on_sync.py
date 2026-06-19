from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pve_sync_plugin', '0010_pvedriftevent'),
    ]

    operations = [
        migrations.AddField(
            model_name='pveclusterconfig',
            name='notify_on_sync',
            field=models.BooleanField(
                default=True,
                help_text='同步時是否發送 Telegram 通知（含同步開始/完成、漂移偵測等）',
            ),
        ),
    ]
