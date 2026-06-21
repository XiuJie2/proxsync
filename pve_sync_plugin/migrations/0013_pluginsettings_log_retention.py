from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pve_sync_plugin", "0012_pvedriftevent_tags_and_index_renames"),
    ]

    operations = [
        migrations.AddField(
            model_name="pvepluginsettings",
            name="log_retention_days",
            field=models.PositiveIntegerField(
                default=90,
                help_text="保留同步 Log 及 State DB 歷史資料天數（0 = 不自動清除）",
            ),
        ),
    ]
