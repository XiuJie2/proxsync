"""Navigation items exposed under NetBox's Plugins menu."""

try:
    from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem
except ImportError:  # NetBox 3.x compatibility
    try:
        from extras.plugins import PluginMenu, PluginMenuButton, PluginMenuItem
    except ImportError:
        PluginMenu = None
        from extras.plugins import PluginMenuButton, PluginMenuItem

try:
    from netbox.choices import ButtonColorChoices
except ImportError:
    try:
        from utilities.choices import ButtonColorChoices
    except ImportError:
        ButtonColorChoices = None


def _button_color(name, fallback):
    if ButtonColorChoices is None:
        return fallback
    return getattr(ButtonColorChoices, name, fallback)


dashboard_item = PluginMenuItem(
    link="plugins:pve_sync_plugin:dashboard",
    link_text="Dashboard",
    permissions=["pve_sync_plugin.view_pvesyncjob"],
    buttons=(
        PluginMenuButton(
            "plugins:pve_sync_plugin:trigger-sync",
            "Run sync",
            "mdi mdi-sync",
            _button_color("GREEN", "green"),
            permissions=["pve_sync_plugin.add_pvesyncjob"],
        ),
    ),
)

clusters_item = PluginMenuItem(
    link="plugins:pve_sync_plugin:cluster-list",
    link_text="PVE Clusters",
    permissions=["pve_sync_plugin.view_pveclusterconfig"],
    buttons=(
        PluginMenuButton(
            "plugins:pve_sync_plugin:cluster-add",
            "Add cluster",
            "mdi mdi-plus-thick",
            _button_color("GREEN", "green"),
            permissions=["pve_sync_plugin.add_pveclusterconfig"],
        ),
    ),
)

settings_item = PluginMenuItem(
    link="plugins:pve_sync_plugin:settings",
    link_text="Settings",
    permissions=["pve_sync_plugin.change_pvepluginsettings"],
)

menu_items = (
    dashboard_item,
    clusters_item,
    settings_item,
)

if PluginMenu is not None:
    menu = PluginMenu(
        label="PVE Sync",
        groups=(
            ("Operations", (dashboard_item,)),
            ("Configuration", (settings_item, clusters_item)),
        ),
        icon_class="mdi mdi-server-network",
    )
