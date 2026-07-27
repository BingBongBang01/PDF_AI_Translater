from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QFileDialog
from PySide6.QtCore import Qt

from ui.windows.base_page import BasePage
from ui.widgets.m3_components import MaterialLabel, MaterialTextEdit
from ui.widgets.material_button import MaterialButton
from utils.i18n import tr
from utils.logger import app_logger, MAX_DISPLAY_LINES

try:
    from config.config import __version__ as APP_VERSION
except ImportError:
    APP_VERSION = "6.0.1"


class AboutPage(BasePage):
    def setup_ui(self):
        lbl = MaterialLabel(f"{tr('About')} (PDF Translater)\n{tr('Version')} {APP_VERSION}")
        lbl.setStyleSheet("font-size: 24px;")
        self.layout.addWidget(lbl)

        # --- Log panel fills the remaining space below the version info ---
        log_header = QHBoxLayout()
        log_title = MaterialLabel(tr("Application Log"))
        log_title.setProperty('m3_typography', 'title_medium')
        log_header.addWidget(log_title)
        log_header.addStretch()

        self.btn_clear = MaterialButton(tr("Clear"))
        self.btn_copy = MaterialButton(tr("Copy"))
        self.btn_export = MaterialButton(tr("Export Log"))
        log_header.addWidget(self.btn_clear)
        log_header.addWidget(self.btn_copy)
        log_header.addWidget(self.btn_export)
        self.layout.addLayout(log_header)

        self.log_view = MaterialTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText(tr("No log entries yet."))
        self.layout.addWidget(self.log_view, 1)

        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_copy.clicked.connect(self.log_view.selectAll)
        self.btn_export.clicked.connect(self._on_export)

        self._refresh_view()
        app_logger.entry_added.connect(self._on_entry_added)

    def _refresh_view(self):
        self.log_view.setPlainText("\n".join(app_logger.recent(MAX_DISPLAY_LINES)))
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def _on_entry_added(self, line: str):
        self.log_view.append(line)
        doc = self.log_view.document()
        if doc.blockCount() > MAX_DISPLAY_LINES:
            cursor = self.log_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            excess = doc.blockCount() - MAX_DISPLAY_LINES
            for _ in range(excess):
                cursor.select(cursor.SelectionType.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()

    def _on_clear(self):
        app_logger.clear()
        self.log_view.clear()

    def _on_export(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Export Log"), "pdf_translater_log.txt", "Text Files (*.txt)"
        )
        if not file_path:
            return
        app_logger.export_to_file(file_path)
        app_logger.info(f"Log exported to {file_path}")
