import sys
from PySide6.QtWidgets import QApplication
from ui.windows.main_window import MainWindow
from ui.themes.theme_manager import ThemeManager
from core.service_locator import ServiceLocator
from core.cache_manager import CacheManager
from utils.logger import install_terminal_log_bridge


def bootstrap_services():
    """Registers process-wide singletons resolved via core.service_locator.resolve()."""
    ServiceLocator.register(CacheManager, CacheManager)


def main():
    install_terminal_log_bridge()
    bootstrap_services()
    app = QApplication(sys.argv)

    # Apply Material Design Theme
    ThemeManager.apply_theme(app)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
