from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QApplication
)
from PySide6.QtCore import Qt, Signal
from ui.widgets.m3_components import MaterialLabel, MaterialFrame, MaterialScrollArea
import sys
import platform
import os
from pathlib import Path
from ui.windows.base_page import BasePage
from ui.widgets.action_card import ActionCard
from ui.widgets.recent_files_table import RecentFilesTable
from ui.widgets.info_card import InfoCard
from ui.widgets.recent_jobs_card import RecentJobsCard
from ui.widgets.file_drop_area import FileDropArea
from models.settings import SettingsManager
from utils.i18n import tr

try:
    from config.config import __version__ as APP_VERSION
except ImportError:
    APP_VERSION = "6.0.1"

def get_dir_size(path: Path) -> str:
    total_size = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
    except Exception:
        pass
    return f"{total_size / (1024*1024):.2f} MB"

class HomePage(BasePage):
    navigate_requested = Signal(int)

    def setup_ui(self):
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = MaterialScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(MaterialFrame.NoFrame)
        
        container = QWidget()
        scroll.setWidget(container)
        
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(24)
        
        # 1. Page Header
        header_layout = QVBoxLayout()
        lbl_title = MaterialLabel("PDF Translater")
        lbl_title.setProperty('m3_typography', 'display_small')
        
        lbl_subtitle = MaterialLabel(f"{tr('Version')} {APP_VERSION}  |  {tr('Theme')}: {SettingsManager().settings.theme}")
        lbl_subtitle.setProperty('m3_typography', 'title_medium')
        
        # Color mapping requires updating stylesheet dynamically via design_system if we want exact colors 
        # that are not just on_surface. We can do that by accessing the global system if needed, 
        # or just relying on base QSS text color. For M3, primary color on text is often used for titles.
        app = QApplication.instance()
        ds = app.property("m3_design_system") if app else None
        if ds:
            lbl_title.setStyleSheet(f"color: {ds.colors.primary};")
            lbl_subtitle.setStyleSheet(f"color: {ds.colors.on_surface_variant};")

        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_subtitle)
        main_layout.addLayout(header_layout)
        
        # 2. Quick Actions
        actions_layout = QHBoxLayout()
        actions = [
            (tr("Open PDF"), tr("Load a new document"), 1),
            (tr("Recent Files"), tr("View history"), 5),
            (tr("Start Translation"), tr("Run active engine"), 2),
            (tr("OCR Image"), tr("Extract text"), 3),
            (tr("Settings"), tr("Configure app"), 6)
        ]
        
        for title, desc, target_idx in actions:
            card = ActionCard(title, desc)
            card.clicked.connect(lambda idx=target_idx: self.navigate_requested.emit(idx))
            actions_layout.addWidget(card)
            
        main_layout.addLayout(actions_layout)
        
        # 3. Drag & Drop
        drop_area = FileDropArea()
        drop_area.setMinimumHeight(150)
        main_layout.addWidget(drop_area)
        
        # 4. Recent Files (Table)
        recent_lbl = MaterialLabel(tr("Recent Files"))
        recent_lbl.setProperty('m3_typography', 'headline_medium')
        main_layout.addWidget(recent_lbl)
        
        table = RecentFilesTable()
        table.load_mock_data()
        main_layout.addWidget(table)
        
        # 5. System Status and App Info Layout
        bottom_layout = QHBoxLayout()
        
        # System Status
        system_stats = {
            tr("OS"): f"{platform.system()} {platform.release()}",
            tr("Python"): sys.version.split()[0],
            tr("Theme"): SettingsManager().settings.theme,
            tr("Engine"): SettingsManager().settings.runtime,
        }
        status_card = InfoCard(tr("System Status"), system_stats)
        bottom_layout.addWidget(status_card)

        # App Info
        config_dir = Path(os.environ.get("APPDATA") or Path.home()) / "PDFTranslaterGUI"
        app_stats = {
            tr("Config Dir"): str(config_dir),
            tr("Cache Size"): get_dir_size(config_dir),
        }
        app_card = InfoCard(tr("Application Information"), app_stats)
        bottom_layout.addWidget(app_card)
        
        main_layout.addLayout(bottom_layout)
        
        # 6. Recent Jobs
        jobs_card = RecentJobsCard()
        main_layout.addWidget(jobs_card)
        
        main_layout.addStretch()
        self.layout.addWidget(scroll)

    def on_show(self):
        pass
