"""PVE Sync engine subpackage.

Provides the core synchronization logic, config bridging,
and state management — usable from both the NetBox plugin
and the standalone ``python sync.py`` CLI.
"""

from .engine import PVESyncEngine  # noqa: F401
