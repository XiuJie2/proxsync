from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pve_sync_plugin", "0019_pluginsettings_telegram_chat_id_backup"),
    ]

    operations = [
        migrations.AddField(
            model_name="pvepluginsettings",
            name="backup_watch_tag",
            field=models.CharField(
                blank=True,
                default="0N",
                max_length=50,
                help_text="VM 標籤：有此標籤的 VM 才會被監控備份逾期（留空則停用備份逾期監控）",
            ),
        ),
        migrations.AddField(
            model_name="pvepluginsettings",
            name="backup_ignore_tag",
            field=models.CharField(
                blank=True,
                default="NO-Backup",
                max_length=50,
                help_text="VM 標籤：有此標籤的 VM 一律忽略備份逾期檢查（不需要備份）",
            ),
        ),
    ]
