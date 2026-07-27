from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog
)
from PySide6.QtCore import Qt
from ui.widgets.m3_components import MaterialLabel, MaterialTextEdit, MaterialSplitter, MaterialTabWidget, MaterialSpinBox, MaterialCheckBox, MirroredLogTextEdit

from ui.widgets.material_button import MaterialButton

import os
import time
import fitz

from ui.windows.base_page import BasePage
from ui.widgets.translation_settings_panel import TranslationSettingsPanel
from ui.widgets.prompt_editor_panel import PromptEditorPanel
from ui.widgets.glossary_manager_panel import GlossaryManagerPanel
from ui.widgets.stats_dashboard import StatsDashboard
from ui.widgets.task_queue_table import TaskQueueTable
from models.settings import SettingsManager
from controllers.translation_controller import TranslationController
from controllers.history_controller import HistoryController
from utils.i18n import tr

class TranslatePage(BasePage):
    def setup_ui(self):
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.controller = TranslationController(self)
        self.controller.translation_ready.connect(self.on_translation_ready)
        self.controller.translation_failed.connect(self.on_translation_failed)
        self.history = HistoryController(self)
        self._start_time = None
        self.current_pdf_path = None
        self.total_pdf_pages = 0

        # --- Top Toolbar ---
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: var(--md-sys-color-surface); border-bottom: 1px solid var(--md-sys-color-outline-variant);")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 8, 16, 8)

        self.btn_open_pdf = MaterialButton(tr("Open PDF"))
        self.btn_translate = MaterialButton(tr("Translate"))
        self.btn_translate.setStyleSheet("background-color: var(--md-sys-color-primary); color: var(--md-sys-color-on-primary); font-weight: bold;")
        self.btn_pause = MaterialButton(tr("Pause"))
        self.btn_resume = MaterialButton(tr("Resume"))
        self.btn_stop = MaterialButton(tr("Stop"))
        self.btn_save = MaterialButton(tr("Save Session"))
        self.btn_load = MaterialButton(tr("Load Session"))

        self.btn_open_pdf.clicked.connect(self.on_open_pdf_clicked)
        self.btn_translate.clicked.connect(self.on_translate_clicked)
        self.btn_stop.clicked.connect(self.on_stop_clicked)
        self.btn_save.clicked.connect(self.on_save_session)
        self.btn_load.clicked.connect(self.on_load_session)
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)

        for btn in [self.btn_open_pdf, self.btn_translate, self.btn_pause, self.btn_resume, self.btn_stop, self.btn_save, self.btn_load]:
            tb_layout.addWidget(btn)
        tb_layout.addStretch()
        self.layout.addWidget(toolbar)
        
        # --- Main Layout ---
        self.main_splitter = MaterialSplitter(Qt.Vertical)
        self.layout.addWidget(self.main_splitter, 1)
        
        # Upper Area
        self.upper_splitter = MaterialSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self.upper_splitter)
        
        # Left Panel (Original Text + Navigator)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        
        nav_layout = QHBoxLayout()
        self.chk_all_pages = MaterialCheckBox(tr("Translate All Pages"))
        self.chk_all_pages.setChecked(True)
        nav_layout.addWidget(self.chk_all_pages)
        nav_layout.addWidget(MaterialLabel(f"<b>{tr('Page')}:</b>"))
        self.page_spin = MaterialSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setEnabled(False)
        nav_layout.addWidget(self.page_spin)
        nav_layout.addStretch()
        left_layout.addLayout(nav_layout)

        self.chk_all_pages.toggled.connect(self.on_page_selection_changed)
        self.page_spin.valueChanged.connect(self.on_page_selection_changed)

        self.original_text = MaterialTextEdit()
        self.original_text.setReadOnly(True)
        self.original_text.setPlaceholderText(tr("Original text..."))
        left_layout.addWidget(MaterialLabel(f"<b>{tr('Original Text')}</b>"))
        left_layout.addWidget(self.original_text)
        
        # Center Panel (Translation Result + Live Preview)
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(8, 8, 8, 8)
        
        self.translation_result = MaterialTextEdit()
        self.translation_result.setPlaceholderText(tr("Translation result..."))
        center_layout.addWidget(MaterialLabel(f"<b>{tr('Translation Result')}</b>"))
        center_layout.addWidget(self.translation_result)

        self.live_preview = MaterialTextEdit()
        self.live_preview.setReadOnly(True)
        self.live_preview.setPlaceholderText(tr("Live Preview render..."))
        center_layout.addWidget(MaterialLabel(f"<b>{tr('Live Preview')}</b>"))
        center_layout.addWidget(self.live_preview)
        
        # Right Panel (Tabs)
        self.right_tabs = MaterialTabWidget()
        self.settings_panel = TranslationSettingsPanel()
        self.prompt_editor = PromptEditorPanel()
        self.glossary_panel = GlossaryManagerPanel()
        
        self.right_tabs.addTab(self.settings_panel, tr("Settings"))
        self.right_tabs.addTab(self.prompt_editor, tr("Prompt"))
        self.right_tabs.addTab(self.glossary_panel, tr("Glossary"))
        
        self.upper_splitter.addWidget(left_panel)
        self.upper_splitter.addWidget(center_panel)
        self.upper_splitter.addWidget(self.right_tabs)
        
        sizes = SettingsManager().settings.translation_panel_sizes
        if len(sizes) == 3:
            self.upper_splitter.setSizes(sizes)
        
        # Bottom Area (Tabs: Queue, Stats, Log)
        self.bottom_tabs = MaterialTabWidget()
        
        headers = [tr("Chunk ID"), tr("Page"), tr("Status"), tr("Progress"), tr("Retries"), tr("ETA"), tr("Provider")]
        mock_queue = [
            ("CHK-001", "1", tr("Completed"), "100%", "0", "-", "Google Gemini"),
            ("CHK-002", "1", tr("Completed"), "100%", "0", "-", "Google Gemini"),
            ("CHK-003", "2", tr("In Progress"), "45%", "0", "1m 30s", "Google Gemini"),
            ("CHK-004", "2", tr("Queued"), "0%", "0", "-", "Google Gemini")
        ]
        self.queue_table = TaskQueueTable(headers)
        self.queue_table.load_data(mock_queue)

        self.stats_panel = StatsDashboard(title=None, stats_dict={tr("Pages"): "0 / 0", tr("Chunks"): "0 / 0", tr("Characters"): "0", tr("Tokens"): "0", tr("Estimated Cost"): "$0.00", tr("Elapsed Time"): "00:00:00"}, has_progress=True)
        
        self.log_viewer = MirroredLogTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setPlaceholderText(tr("System Logs will appear here..."))
        
        self.bottom_tabs.addTab(self.queue_table, tr("Translation Queue"))
        self.bottom_tabs.addTab(self.stats_panel, tr("Statistics"))
        self.bottom_tabs.addTab(self.log_viewer, tr("System Log"))
        
        self.main_splitter.addWidget(self.bottom_tabs)
        
    def on_open_pdf_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(self, tr("Open PDF"), "", tr("PDF Files") + " (*.pdf)")
        if file_path:
            self.load_pdf(file_path)

    def load_pdf(self, file_path, page_index=None):
        """Load a PDF for translation. If page_index is given, translate just
        that page; otherwise default to translating the whole document."""
        try:
            doc = fitz.open(file_path)
            page_count = len(doc)
            doc.close()
        except Exception as e:
            self.log_viewer.append(f"[ERROR] {tr('Failed to open PDF')}: {e}")
            return

        self.current_pdf_path = file_path
        self.total_pdf_pages = page_count
        self.page_spin.setRange(1, max(page_count, 1))

        if page_index is not None:
            self.chk_all_pages.setChecked(False)
            self.page_spin.setValue(min(page_index + 1, page_count))
        else:
            self.chk_all_pages.setChecked(True)

        self._refresh_extracted_text()
        self.log_viewer.append(f"[INFO] {tr('Loaded')} {os.path.basename(file_path)} ({page_count} {tr('pages')})")

    def on_page_selection_changed(self, *_args):
        self.page_spin.setEnabled(not self.chk_all_pages.isChecked())
        if self.current_pdf_path:
            self._refresh_extracted_text()

    def _refresh_extracted_text(self):
        if not self.current_pdf_path:
            return
        try:
            doc = fitz.open(self.current_pdf_path)
            if self.chk_all_pages.isChecked():
                text = "\n\n".join(doc.load_page(i).get_text() for i in range(len(doc)))
            else:
                page_num = self.page_spin.value() - 1
                text = doc.load_page(page_num).get_text()
            doc.close()
        except Exception as e:
            self.log_viewer.append(f"[ERROR] {tr('Failed to open PDF')}: {e}")
            return
        self.original_text.setPlainText(text)

    def on_translate_clicked(self):
        text = self.original_text.toPlainText().strip()
        if not text:
            self.log_viewer.append(f"[WARN] {tr('No source text to translate. Load a PDF page or paste text first.')}")
            return

        source_lang = self.settings_panel.cb_src.currentText()
        target_lang = self.settings_panel.cb_tgt.currentText()
        provider = self.settings_panel.cb_provider.currentText()

        if not self.controller.select_provider(provider):
            self.log_viewer.append(f"[ERROR] {tr('Provider')} '{provider}' {tr('is unavailable (check API key in Settings).')}")
            return

        self.btn_translate.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._start_time = time.time()
        self._last_provider = provider
        self._last_langs = (source_lang, target_lang)
        self.log_viewer.append(f"[INFO] {tr('Translation started')} ({provider}, {source_lang} -> {target_lang})...")
        self.controller.translate_async(text, source_lang, target_lang)

    def on_translation_ready(self, result_text):
        self.btn_translate.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.translation_result.setText(result_text)
        self.live_preview.setHtml(f"<p>{result_text}</p>")
        self.log_viewer.append(f"[INFO] {tr('Translation completed successfully.')}")

        elapsed = time.time() - self._start_time if self._start_time else 0
        chars = len(self.original_text.toPlainText())
        self.stats_panel.update_stats({
            tr("Pages"): "1 / 1",
            tr("Chunks"): "1 / 1",
            tr("Characters"): str(chars),
            tr("Tokens"): "-",
            tr("Estimated Cost"): "-",
            tr("Elapsed Time"): time.strftime("%H:%M:%S", time.gmtime(elapsed)),
        }, progress_val=100)

        source_lang, target_lang = getattr(self, "_last_langs", ("-", "-"))
        self.history.add_history("Translate", {
            "provider": getattr(self, "_last_provider", "-"),
            "status": tr("Completed"),
            "duration": time.strftime("%H:%M:%S", time.gmtime(elapsed)),
            "file": f"{source_lang} -> {target_lang}",
        })

    def on_translation_failed(self, error_msg):
        self.btn_translate.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log_viewer.append(f"[ERROR] {tr('Translation failed')}: {error_msg}")

    def on_stop_clicked(self):
        self.controller.stop()
        self.btn_translate.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log_viewer.append(f"[INFO] {tr('Translation stopped by user.')}")

    def on_save_session(self):
        file_path, _ = QFileDialog.getSaveFileName(self, tr("Save Session"), "", tr("Text Files") + " (*.txt)")
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("=== Original ===\n")
            f.write(self.original_text.toPlainText())
            f.write("\n\n=== Translation ===\n")
            f.write(self.translation_result.toPlainText())
        self.log_viewer.append(f"[INFO] {tr('Session saved to')} {file_path}")

    def on_load_session(self):
        file_path, _ = QFileDialog.getOpenFileName(self, tr("Load Session"), "", tr("Text Files") + " (*.txt)")
        if not file_path:
            return
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "=== Translation ===" in content:
            original, translation = content.split("=== Translation ===", 1)
            self.original_text.setPlainText(original.replace("=== Original ===", "").strip())
            self.translation_result.setPlainText(translation.strip())
        else:
            self.original_text.setPlainText(content)
        self.log_viewer.append(f"[INFO] {tr('Session loaded from')} {file_path}")


    def hideEvent(self, event):
        SettingsManager().settings.translation_panel_sizes = self.upper_splitter.sizes()
        SettingsManager().save()
        super().hideEvent(event)
