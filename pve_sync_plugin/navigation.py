"""Navigation items exposed under NetBox's Plugins menu."""

from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

from netbox.choices import ButtonColorChoices


dashboard_item = PluginMenuItem(
    link="plugins:pve_sync_plugin:dashboard",
    link_text="Dashboard",
    permissions=["pve_sync_plugin.view_pvesyncjob"],
    buttons=(
        PluginMenuButton(
            "plugins:pve_sync_plugin:trigger-sync",
            "Run sync",
            "mdi mdi-sync",
            ButtonColorChoices.GREEN,
            permissions=["pve_sync_plugin.add_pvesyncjob"],
        ),
    ),
)

jobs_item = PluginMenuItem(
    link="plugins:pve_sync_plugin:pvesyncjob_list",
    link_text="Sync Jobs",
    permissions=["pve_sync_plugin.view_pvesyncjob"],
)

events_item = PluginMenuItem(
    link="plugins:pve_sync_plugin:pvewebhookevent_list",
    link_text="Webhook Events",
    permissions=["pve_sync_plugin.view_pvewebhookevent"],
)

clusters_item = PluginMenuItem(
    link="plugins:pve_sync_plugin:pveclusterconfig_list",
    link_text="PVE Clusters",
    permissions=["pve_sync_plugin.view_pveclusterconfig"],
    buttons=(
        PluginMenuButton(
            "plugins:pve_sync_plugin:pveclusterconfig_add",
            "Add cluster",
            "mdi mdi-plus-thick",
            ButtonColorChoices.GREEN,
            permissions=["pve_sync_plugin.add_pveclusterconfig"],
        ),
    ),
)

backup_status_item = PluginMenuItem(
    link="plugins:pve_sync_plugin:pvebackupstatus_list",
    link_text="Backup Status",
    permissions=["pve_sync_plugin.view_pvebackupstatus"],
)

settings_item = PluginMenuItem(
    link="plugins:pve_sync_plugin:settings",
    link_text="Settings",
    permissions=["pve_sync_plugin.change_pvepluginsettings"],
)


menu = PluginMenu(
    label="PVE Sync",
    groups=(
        (
            "Overview",
            (dashboard_item,),
        ),
        (
            "Sync & Operations",
            (jobs_item, events_item),
        ),
        (
            "Data Protection",
            (backup_status_item,),
        ),
        (
            "Configuration",
            (clusters_item, settings_item),
        ),
    ),
    icon_class="mdi mdi-server-network",
)
