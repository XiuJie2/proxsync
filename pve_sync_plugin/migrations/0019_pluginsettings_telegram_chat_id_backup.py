from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pve_sync_plugin", "0018_vmprovisioninglog_remove_in_progress_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="pvepluginsettings",
            name="telegram_chat_id_backup",
            field=models.CharField(
                blank=True,
                max_length=100,
                help_text="備份異常通知專用群組（留空則沿用上方的一般通知 Chat ID）",
            ),
        ),
    ]
