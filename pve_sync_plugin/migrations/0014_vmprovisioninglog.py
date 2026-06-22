from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pve_sync_plugin", "0013_pluginsettings_log_retention"),
        ("extras", "0138_customfieldchoiceset_choice_colors"),
    ]

    operations = [
        migrations.CreateModel(
            name="VmProvisioningLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=None)),
                ("vm_name",       models.CharField(max_length=100, verbose_name="VM 名稱")),
                ("vmid",          models.IntegerField(blank=True, null=True, verbose_name="VMID")),
                ("cluster_name",  models.CharField(blank=True, max_length=100, verbose_name="叢集")),
                ("node",          models.CharField(blank=True, max_length=100, verbose_name="節點")),
                ("os_type",       models.CharField(blank=True, max_length=50,  verbose_name="作業系統")),
                ("cpu",           models.IntegerField(blank=True, null=True,   verbose_name="CPU")),
                ("ram_gb",        models.IntegerField(blank=True, null=True,   verbose_name="記憶體 (GB)")),
                ("disk_gb",       models.IntegerField(blank=True, null=True,   verbose_name="磁碟 (GB)")),
                ("management_ip", models.CharField(blank=True, max_length=50,  verbose_name="Management IP")),
                ("management_gw", models.CharField(blank=True, max_length=50,  verbose_name="Management 閘道")),
                ("internet_ip",   models.CharField(blank=True, max_length=50,  verbose_name="Internet IP")),
                ("internet_gw",   models.CharField(blank=True, max_length=50,  verbose_name="Internet 閘道")),
                ("status",        models.CharField(
                    choices=[("planning", "規劃中"), ("in_progress", "部署中"), ("completed", "完成")],
                    default="planning", max_length=20, verbose_name="狀態",
                )),
                ("notes",         models.TextField(blank=True, verbose_name="備註")),
                ("checklist",     models.JSONField(blank=True, default=dict, verbose_name="清單狀態")),
            ],
            options={"ordering": ["-created"], "verbose_name": "VM Provisioning Log"},
        ),
    ]
