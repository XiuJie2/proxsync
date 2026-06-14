from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pve_sync_plugin', '0007_rename_verbose_names_to_proxmox_sync'),
    ]

    operations = [
        migrations.AddField(
            model_name='pbsserverconfig',
            name='sync_schedule',
            field=models.CharField(
                choices=[
                    ('disabled', 'Disabled'),
                    ('hourly', 'Hourly'),
                    ('every_6h', 'Every 6 hours'),
                    ('daily', 'Daily'),
                    ('weekly', 'Weekly'),
                ],
                default='disabled',
                max_length=20,
            ),
        ),
    ]
