from django.db import migrations, models


SCHEDULE_CHOICES = [
    ('disabled', 'Disabled'),
    ('hourly', 'Hourly'),
    ('every_3h', 'Every 3 hours'),
    ('every_6h', 'Every 6 hours'),
    ('daily', 'Daily'),
    ('weekly', 'Weekly'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('pve_sync_plugin', '0008_pbsserverconfig_sync_schedule'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pveclusterconfig',
            name='sync_schedule',
            field=models.CharField(
                choices=SCHEDULE_CHOICES,
                default='disabled',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='pbsserverconfig',
            name='sync_schedule',
            field=models.CharField(
                choices=SCHEDULE_CHOICES,
                default='disabled',
                max_length=20,
            ),
        ),
    ]
