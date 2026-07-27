import json
from pathlib import Path
from typing import Any, Dict, List
from core.exceptions import ConfigurationError
from core.logger import logger
from core.event_bus import EventBus

class ConfigManager:
    """Manages application JSON configuration with schemas, validation, profiles and auto-migration."""
    def __init__(self, config_path: str = "config/app_config.json"):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = self._default_config()
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "version": "1.0",
            "active_profile": "default",
            "translation": {
                "provider": "google",
                "model": "gemini-2.5-pro",
                "temperature": 0.3,
                "max_tokens": 8192
            },
            "ocr": {
                "engine": "tesseract",
                "language": "eng",
                "dpi": 300
            },
            "pdf": {
                "default_zoom": 100,
                "cache_size_mb": 512
            }
        }

    def _load(self):
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                self._migrate(data)
                self.config.update(data.get("config", {}))
                self.profiles = data.get("profiles", {"default": self.config.copy()})
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                raise ConfigurationError(f"Config load error: {e}")
        else:
            self.profiles["default"] = self.config.copy()
            self.save()

    def _migrate(self, data: Dict[str, Any]):
        pass

    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "config": self.config,
                "profiles": self.profiles
            }
            self.config_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise ConfigurationError(f"Config save error: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        val = self.config
        try:
            for k in keys:
                val = val[k]
            return val
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any):
        keys = key.split(".")
        target = self.config
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        
        active = self.config.get("active_profile", "default")
        self.profiles[active] = self.config.copy()
        
        self.save()
        EventBus.publish("SettingsChanged", key)

    def switch_profile(self, profile_name: str):
        if profile_name in self.profiles:
            self.config = self.profiles[profile_name].copy()
            self.config["active_profile"] = profile_name
            self.save()
            EventBus.publish("ProfileSwitched", profile_name)
            
    def save_profile(self, profile_name: str):
        self.profiles[profile_name] = self.config.copy()
        self.config["active_profile"] = profile_name
        self.save()

    def backup(self, backup_path: str):
        Path(backup_path).write_text(json.dumps({"config": self.config, "profiles": self.profiles}, indent=4, ensure_ascii=False), encoding="utf-8")

    def restore(self, backup_path: str):
        if Path(backup_path).exists():
            data = json.loads(Path(backup_path).read_text(encoding="utf-8"))
            self.config = data.get("config", self._default_config())
            self.profiles = data.get("profiles", {"default": self.config})
            self.save()
