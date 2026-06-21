import importlib
import logging

logger = logging.getLogger(__name__)


class PVESyncEngine:
    """Plugin-facing wrapper around the standalone OptimizedPVEToNetBoxSync.

    Usage in tasks.py::

        from pve_sync_plugin.sync import PVESyncEngine

        engine = PVESyncEngine(config_path="/tmp/pve-sync-xxx.yaml")
        engine.run()
        stats = engine.stats
    """

    def __init__(self, config_path=None, job_id=None):
        self.config_path = config_path
        self.job_id = job_id
        self._sync_instance = None
        self.stats = {}

    def run(self):
        """Execute a full sync cycle using the standalone engine."""
        try:
            config_module = importlib.import_module("config")
            sync_module = importlib.import_module("pve_sync")
        except ImportError as exc:
            logger.error(
                "Cannot import standalone sync modules. "
                "Make sure the project root is accessible: %s",
                exc,
            )
            raise

        # Re-initialize config with our temp file
        if self.config_path:
            config_module._global_config = None
            config_module.init_config(self.config_path)

        # Run the sync
        self._sync_instance = sync_module.OptimizedPVEToNetBoxSync(job_id=self.job_id)
        self._sync_instance.sync()

        # Capture stats
        self.stats = dict(getattr(self._sync_instance, "stats", {}))

        return self.stats
