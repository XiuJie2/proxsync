"""Data steps for 0022, kept in their own migration: PostgreSQL refuses the
index creation of a schema migration once rows of the same table were
updated in that transaction ("pending trigger events")."""

from django.db import migrations

import pve_sync_plugin.fields

# Secret fields per model: encrypted at rest and masked in the changelog.
ENCRYPTED = {
    "pveclusterconfig": ["pve_secret"],
    "pbsserverconfig": ["pbs_token_secret"],
    "veeamserverconfig": ["password"],
}
MASKED = {
    **ENCRYPTED,
    "pvepluginsettings": ["netbox_token", "telegram_bot_token", "webhook_secret"],
}


def encrypt_existing_secrets(apps, schema_editor):
    # The historical models use EncryptedTextField: plaintext rows read back
    # unchanged and get encrypted when written with update().
    for model_name, fields in ENCRYPTED.items():
        Model = apps.get_model("pve_sync_plugin", model_name)
        for obj in Model.objects.all():
            Model.objects.filter(pk=obj.pk).update(**{f: getattr(obj, f) for f in fields})


def link_pbs_devices(apps, schema_editor):
    PbsServerConfig = apps.get_model("pve_sync_plugin", "PbsServerConfig")
    Device = apps.get_model("dcim", "Device")
    for pbs in PbsServerConfig.objects.filter(netbox_device__isnull=True):
        device = Device.objects.filter(name=pbs.pbs_node_name).first()
        if device:
            PbsServerConfig.objects.filter(pk=pbs.pk).update(netbox_device=device)


def link_veeam_hosts(apps, schema_editor):
    """Link Veeam configs to the NetBox device/VM that owns their host IP."""
    import ipaddress

    VeeamServerConfig = apps.get_model("pve_sync_plugin", "VeeamServerConfig")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Interface = apps.get_model("dcim", "Interface")
    VMInterface = apps.get_model("virtualization", "VMInterface")
    for server in VeeamServerConfig.objects.filter(netbox_device__isnull=True, netbox_vm__isnull=True):
        try:
            ipaddress.ip_address(server.host.strip())
        except ValueError:
            continue
        for ip in IPAddress.objects.filter(address__net_host=server.host.strip()).select_related("assigned_object_type"):
            model = ip.assigned_object_type.model if ip.assigned_object_type else None
            if model == "interface":
                iface = Interface.objects.filter(pk=ip.assigned_object_id).first()
                if iface:
                    VeeamServerConfig.objects.filter(pk=server.pk).update(netbox_device_id=iface.device_id)
                    break
            elif model == "vminterface":
                iface = VMInterface.objects.filter(pk=ip.assigned_object_id).first()
                if iface:
                    VeeamServerConfig.objects.filter(pk=server.pk).update(netbox_vm_id=iface.virtual_machine_id)
                    break


def mask_changelog_secrets(apps, schema_editor):
    ObjectChange = apps.get_model("core", "ObjectChange")
    ContentType = apps.get_model("contenttypes", "ContentType")
    for model_name, fields in MASKED.items():
        ct = ContentType.objects.filter(app_label="pve_sync_plugin", model=model_name).first()
        if ct is None:
            continue
        for change in ObjectChange.objects.filter(changed_object_type=ct):
            updates = {}
            for attr in ("prechange_data", "postchange_data"):
                data = getattr(change, attr)
                if isinstance(data, dict) and any(data.get(f) for f in fields):
                    updates[attr] = pve_sync_plugin.fields.mask_secrets(dict(data), fields)
            if updates:
                ObjectChange.objects.filter(pk=change.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '__latest__'),
        ('core', '__latest__'),
        ('ipam', '__latest__'),
        ('pve_sync_plugin', '0022_backup_monitoring_and_secrets'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_secrets, migrations.RunPython.noop),
        migrations.RunPython(link_pbs_devices, migrations.RunPython.noop),
        migrations.RunPython(link_veeam_hosts, migrations.RunPython.noop),
        migrations.RunPython(mask_changelog_secrets, migrations.RunPython.noop),
    ]
