from typing import Dict, List, Any, Optional
from core.logger import logger
from core.exceptions import PluginError

class PluginMetadata:
    def __init__(self, name: str, version: str, category: str, capabilities: List[str]):
        self.name = name
        self.version = version
        self.category = category
        self.capabilities = capabilities
        self.enabled = True
        self.health = "OK"

class PluginManager:
    """Manages dynamic discovery, loading, and lifecycle of application plugins."""
    def __init__(self):
        self.plugins: Dict[str, PluginMetadata] = {}

    def discover(self):
        # Stub for future dynamic discovery (e.g. iterating over a plugins/ dir)
        logger.info("Plugin discovery stub called.")

    def register_plugin(self, metadata: PluginMetadata):
        self.plugins[metadata.name] = metadata
        logger.info(f"Registered plugin: {metadata.name} v{metadata.version} ({metadata.category})")

    def enable_plugin(self, name: str):
        if name in self.plugins:
            self.plugins[name].enabled = True
            logger.info(f"Plugin {name} enabled.")
        else:
            raise PluginError(f"Plugin {name} not found.")

    def disable_plugin(self, name: str):
        if name in self.plugins:
            self.plugins[name].enabled = False
            logger.info(f"Plugin {name} disabled.")
        else:
            raise PluginError(f"Plugin {name} not found.")

    def get_plugins_by_category(self, category: str) -> List[PluginMetadata]:
        return [p for p in self.plugins.values() if p.category == category]
        
    def reload_plugins(self):
        logger.info("Reloading all plugins...")
        self.discover()
