from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget
from PySide6.QtCore import Qt, QByteArray
import base64
from models.settings import SettingsManager

from ui.widgets.navigation_rail import NavigationRail
from ui.widgets.status_bar import MainStatusBar
from ui.widgets.log_dock import LogDock

from ui.windows.pages.home_page import HomePage
from ui.windows.pages.pdf_page import PDFPage
from ui.windows.pages.translate_page import TranslatePage
from ui.windows.pages.ocr_page import OCRPage
from ui.windows.pages.export_page import ExportPage
from ui.windows.pages.history_page import HistoryPage
from ui.windows.pages.settings_page import SettingsPage
from ui.windows.pages.about_page import AboutPage

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Translater v6.0.0")
        self.resize(1200, 800)
        self.setMinimumSize(850, 650)
        
        # Main Layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Navigation Rail
        self.nav_rail = NavigationRail()
        self.main_layout.addWidget(self.nav_rail)
        
        # Stacked Pages
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget, 1)
        
        # Setup Pages
        self.pages = [
            HomePage(),
            PDFPage(),
            TranslatePage(),
            OCRPage(),
            ExportPage(),
            HistoryPage(),
            SettingsPage(),
            AboutPage()
        ]
        
        destinations = [
            ("Home", "Dashboard"),
            ("PDF", "PDF Management"),
            ("Translate", "Translation"),
            ("OCR", "OCR settings"),
            ("Export", "Export outputs"),
            ("History", "History"),
            ("Settings", "Settings"),
            ("About", "About")
        ]
        
        for idx, (icon, tooltip) in enumerate(destinations):
            self.stacked_widget.addWidget(self.pages[idx])
            self.nav_rail.add_destination(icon, tooltip, idx)
            
        self.nav_rail.page_changed.connect(self.change_page)
        
        # Status Bar
        self.status_bar = MainStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Bottom Log Dock
        self.log_dock = LogDock("Logs", self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        
        self.restore_window_state()
        
    def restore_window_state(self):
        settings = SettingsManager().settings
        if settings.window_geometry:
            self.restoreGeometry(QByteArray(base64.b64decode(settings.window_geometry)))
        if settings.window_state:
            self.restoreState(QByteArray(base64.b64decode(settings.window_state)))
            
    def closeEvent(self, event):
        mgr = SettingsManager()
        mgr.settings.window_geometry = base64.b64encode(self.saveGeometry().data()).decode('ascii')
        mgr.settings.window_state = base64.b64encode(self.saveState().data()).decode('ascii')
        mgr.save()
        super().closeEvent(event)
        
    def change_page(self, idx: int):
        self.stacked_widget.setCurrentIndex(idx)
        # Notify page it was shown
        current_page = self.stacked_widget.widget(idx)
        if hasattr(current_page, 'on_show'):
            current_page.on_show()
