"""
Compatibility shim — NetBox uses the PluginConfig defined in __init__.py.
This file is kept so Django does not auto-discover a conflicting AppConfig.
"""
from pve_sync_plugin import PveSyncPluginConfig  # noqa: F401
