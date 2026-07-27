from services.base_service import BaseService
from core.logger import logger
from core.config_manager import ConfigManager

class SettingsService(BaseService):
    """Facade for Settings operations."""
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        
    def update_setting(self, key: str, value):
        logger.info(f"Updating setting {key} to {value}")
        self.config.set(key, value)
        
    def switch_profile(self, profile_name: str):
        logger.info(f"Switching to profile {profile_name}")
        self.config.switch_profile(profile_name)
        
    def save_profile(self, profile_name: str):
        logger.info(f"Saving current settings to profile {profile_name}")
        self.config.save_profile(profile_name)
