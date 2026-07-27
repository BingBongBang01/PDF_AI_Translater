from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget
from PySide6.QtCore import Qt, QByteArray
import base64
from models.settings import SettingsManager
from core.i18n import tr

from ui.widgets.navigation_rail import NavigationRail
from ui.widgets.status_bar import MainStatusBar

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
            (tr("Home"), tr("Dashboard")),
            (tr("PDF"), tr("PDF Management")),
            (tr("Translate"), tr("Translation")),
            (tr("OCR"), tr("OCR settings")),
            (tr("Export"), tr("Export outputs")),
            (tr("History"), tr("History")),
            (tr("Settings"), tr("Settings")),
            (tr("About"), tr("About"))
        ]
        
        for idx, (icon, tooltip) in enumerate(destinations):
            self.stacked_widget.addWidget(self.pages[idx])
            self.nav_rail.add_destination(icon, tooltip, idx)
            
        self.nav_rail.page_changed.connect(self.change_page)
        
        # Connect HomePage navigation
        self.pages[0].navigate_requested.connect(self.change_page_from_home)
        
        # Status Bar
        self.status_bar = MainStatusBar()
        self.setStatusBar(self.status_bar)
        
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
        
    def change_page_from_home(self, idx: int):
        btn = self.nav_rail.btn_group.button(idx)
        if btn:
            btn.setChecked(True)
        self.change_page(idx)
        
    def change_page(self, idx: int):
        self.stacked_widget.setCurrentIndex(idx)
        # Notify page it was shown
        current_page = self.stacked_widget.widget(idx)
        if hasattr(current_page, 'on_show'):
            current_page.on_show()
