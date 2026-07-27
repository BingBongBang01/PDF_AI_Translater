from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QApplication, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QObject
from ui.widgets.m3_components import MaterialLabel, MaterialFrame, MaterialScrollArea, MaterialTextEdit
from ui.widgets.material_button import MaterialButton
import sys
import platform
import os
import shutil
import logging
from pathlib import Path
from ui.windows.base_page import BasePage
from ui.widgets.action_card import ActionCard
from ui.widgets.recent_files_table import RecentFilesTable
from ui.widgets.info_card import InfoCard
from ui.widgets.recent_jobs_card import RecentJobsCard
from ui.widgets.file_drop_area import FileDropArea
from models.settings import SettingsManager
from core.i18n import tr
from core.logger import logger

try:
    from config.config import __version__ as APP_VERSION
except ImportError:
    APP_VERSION = "6.0.0"

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

class LogEmitter(QObject):
    new_log = Signal(str)

class QtLogHandler(logging.Handler):
    def __init__(self, emitter):
        super().__init__()
        self.emitter = emitter
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
    def emit(self, record):
        msg = self.format(record)
        self.emitter.new_log.emit(msg)

class LogViewerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        toolbar = QHBoxLayout()
        lbl = MaterialLabel(tr("System Logs"))
        lbl.setProperty('m3_typography', 'title_medium')
        self.btn_export = MaterialButton(tr("Export Logs"))
        
        toolbar.addWidget(lbl)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_export)
        
        self.text_edit = MaterialTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(500)
        self.text_edit.setMinimumHeight(200)
        
        layout.addLayout(toolbar)
        layout.addWidget(self.text_edit)
        
        self.emitter = LogEmitter()
        self.emitter.new_log.connect(self.text_edit.append)
        
        handler = QtLogHandler(self.emitter)
        logger.addHandler(handler)
        
        self.btn_export.clicked.connect(self.export_logs)
        
    def export_logs(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Logs", "logs.txt", "Text Files (*.txt)")
        if path:
            try:
                if os.path.exists("logs/app.log"):
                    shutil.copy2("logs/app.log", path)
                else:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(self.text_edit.toPlainText())
            except Exception as e:
                self.text_edit.append(f"[ERROR] Failed to export logs: {e}")

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
        lbl_title = MaterialLabel(tr("PDF Translater"))
        lbl_title.setProperty('m3_typography', 'display_small')
        
        lbl_subtitle = MaterialLabel(f"{tr('Version')} {APP_VERSION}  |  {tr('Theme:')} {SettingsManager().settings.theme}")
        lbl_subtitle.setProperty('m3_typography', 'title_medium')
        
        app = QApplication.instance()
        ds = app.property("m3_design_system") if app else None
        if ds:
            lbl_title.setStyleSheet(f"color: {ds.colors.primary};")
            lbl_subtitle.setStyleSheet(f"color: {ds.colors.on_surface_variant};")

        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_subtitle)
        
        # Add Log Viewer below subtitle
        self.log_viewer = LogViewerWidget()
        header_layout.addWidget(self.log_viewer)
        
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
