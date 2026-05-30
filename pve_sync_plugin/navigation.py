"""Navigation items exposed under NetBox's Plugins menu."""

try:
    from netbox.plugins import PluginMenuButton, PluginMenuItem
except ImportError:  # NetBox 3.x compatibility
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


menu_items = (
    PluginMenuItem(
        link="plugins:pve_sync_plugin:dashboard",
        link_text="PVE Sync",
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
    ),
    PluginMenuItem(
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
    ),
)
