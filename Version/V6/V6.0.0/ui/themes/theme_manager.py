import os
from PySide6.QtWidgets import QApplication
from models.settings import SettingsManager
from ui.themes.m3_design_system import M3DesignSystem

class ThemeManager:
    """Manages application themes using Material Design 3 system."""
    @staticmethod
    def apply_theme(app: QApplication = None):
        if app is None:
            app = QApplication.instance()
            
        settings = SettingsManager().settings
        theme_preference = settings.theme # 'light', 'dark', 'system'
        
        # Simple theme resolution. 
        is_dark = (theme_preference == 'dark')
        # If 'system', we'll default to dark for now unless we query the OS.
        if theme_preference == 'system':
            is_dark = True
            
        design_system = M3DesignSystem(is_dark=is_dark)
        
        # Apply custom M3 stylesheet
        app.setStyleSheet(design_system.generate_qss())
        
        # Store active design system in app property so widgets can access tokens dynamically
        app.setProperty("m3_design_system", design_system)
        
    @staticmethod
    def toggle_theme():
        settings = SettingsManager().settings
        settings.theme = 'light' if settings.theme == 'dark' else 'dark'
        SettingsManager().save()
        ThemeManager.apply_theme()
