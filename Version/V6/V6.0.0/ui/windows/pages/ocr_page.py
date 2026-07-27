from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog
)
from PySide6.QtCore import Qt, QRectF
from ui.widgets.m3_components import MaterialLabel, MaterialTextEdit, MaterialSplitter, MaterialTabWidget, MaterialProgressBar, MaterialListWidget

from ui.widgets.material_button import MaterialButton

import os
import time

from ui.windows.base_page import BasePage
from ui.widgets.image_viewer import ImageViewer
from ui.widgets.thumbnail_list import ThumbnailList
from ui.widgets.ocr_settings_panel import OcrSettingsPanel
from ui.widgets.ocr_result_panel import OcrResultPanel
from ui.widgets.task_queue_table import TaskQueueTable
from ui.widgets.stats_dashboard import StatsDashboard
from models.settings import SettingsManager
from controllers.ocr_controller import OCRController
from controllers.history_controller import HistoryController

class OCRPage(BasePage):
    def setup_ui(self):
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.controller = OCRController(self)
        self.controller.ocr_ready.connect(self.on_ocr_ready)
        self.controller.ocr_failed.connect(self.on_ocr_failed)
        self.history = HistoryController(self)
        self.current_image_path = None
        self._start_time = None

        # --- Top Toolbar ---
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: var(--md-sys-color-surface); border-bottom: 1px solid var(--md-sys-color-outline-variant);")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 8, 16, 8)
        
        self.btn_open_img = MaterialButton("Open Image")
        self.btn_open_pdf = MaterialButton("Open PDF")
        self.btn_start = MaterialButton("Start OCR")
        self.btn_start.setStyleSheet("background-color: var(--md-sys-color-primary); color: var(--md-sys-color-on-primary); font-weight: bold;")
        self.btn_pause = MaterialButton("Pause")
        self.btn_resume = MaterialButton("Resume")
        self.btn_stop = MaterialButton("Stop")
        self.btn_save = MaterialButton("Save Result")
        
        self.btn_open_img.clicked.connect(self.on_open_image)
        self.btn_open_pdf.clicked.connect(self.on_open_pdf_for_ocr)
        self.btn_start.clicked.connect(self.on_start_ocr)
        self.btn_stop.clicked.connect(self.on_stop_ocr)
        self.btn_save.clicked.connect(self.on_save_result)
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_stop.setEnabled(False)

        for btn in [self.btn_open_img, self.btn_open_pdf, self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop, self.btn_save]:
            tb_layout.addWidget(btn)
        tb_layout.addStretch()
        self.layout.addWidget(toolbar)
        
        # --- Main Layout ---
        self.main_splitter = MaterialSplitter(Qt.Vertical)
        self.layout.addWidget(self.main_splitter, 1)
        
        # Upper Area
        self.upper_splitter = MaterialSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self.upper_splitter)
        
        # Left Panel (Image List / Thumbnails Tabs)
        self.left_tabs = MaterialTabWidget()
        self.image_list = MaterialListWidget()
        self.image_list.itemClicked.connect(self.on_image_item_clicked)

        self.thumbnail_list = ThumbnailList()
        
        self.left_tabs.addTab(self.image_list, "Images")
        self.left_tabs.addTab(self.thumbnail_list, "Thumbnails")
        
        # Center Panel (Image Viewer)
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        viewer_tools = QHBoxLayout()
        self.btn_pan = MaterialButton("Pan")
        self.btn_pan.setCheckable(True)
        self.btn_select = MaterialButton("Select Region")
        self.btn_select.setCheckable(True)
        self.btn_zoom_in = MaterialButton("Zoom In")
        self.btn_zoom_out = MaterialButton("Zoom Out")
        self.btn_fit = MaterialButton("Fit")
        
        viewer_tools.addWidget(self.btn_pan)
        viewer_tools.addWidget(self.btn_select)
        viewer_tools.addStretch()
        viewer_tools.addWidget(self.btn_zoom_in)
        viewer_tools.addWidget(self.btn_zoom_out)
        viewer_tools.addWidget(self.btn_fit)
        
        self.viewer = ImageViewer()
        self.btn_pan.clicked.connect(lambda: self.viewer.set_mode("pan"))
        self.btn_select.clicked.connect(lambda: self.viewer.set_mode("select"))
        self.btn_zoom_in.clicked.connect(self.viewer.zoom_in)
        self.btn_zoom_out.clicked.connect(self.viewer.zoom_out)
        self.btn_fit.clicked.connect(self.viewer.fit_width)
        self.viewer.region_selected.connect(self.on_region_selected)
        
        center_layout.addLayout(viewer_tools)
        center_layout.addWidget(self.viewer, 1)
        
        # Right Panel (Tabs)
        self.right_tabs = MaterialTabWidget()
        self.result_panel = OcrResultPanel()
        self.settings_panel = OcrSettingsPanel()
        
        self.right_tabs.addTab(self.result_panel, "OCR Result")
        self.right_tabs.addTab(self.settings_panel, "Settings")
        
        self.upper_splitter.addWidget(self.left_tabs)
        self.upper_splitter.addWidget(center_panel)
        self.upper_splitter.addWidget(self.right_tabs)
        
        sizes = SettingsManager().settings.ocr_panel_sizes
        if len(sizes) == 3:
            self.upper_splitter.setSizes(sizes)
        
        # Bottom Area (Tabs: Queue, Stats, Log)
        self.bottom_tabs = MaterialTabWidget()
        
        headers = ["File", "Page", "Status", "Progress", "Confidence", "ETA"]
        mock_queue = [
            ("document.pdf", "1", "Completed", "100%", "98%", "-"),
            ("document.pdf", "2", "Completed", "100%", "95%", "-"),
            ("scan_001.png", "1", "In Progress", "60%", "92%", "45s"),
            ("scan_002.png", "1", "Queued", "0%", "-", "-")
        ]
        self.queue_table = TaskQueueTable(headers)
        self.queue_table.load_data(mock_queue)
        
        self.stats_panel = StatsDashboard(title=None, stats_dict={"Total Images": "0", "Total Pages": "0", "Average Confidence": "0%", "Elapsed Time": "00:00:00", "Estimated Cost": "$0.00"}, has_progress=True)
        
        self.log_viewer = MaterialTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setPlaceholderText("System Logs will appear here...")
        
        self.bottom_tabs.addTab(self.queue_table, "OCR Queue")
        self.bottom_tabs.addTab(self.stats_panel, "Statistics")
        self.bottom_tabs.addTab(self.log_viewer, "System Log")
        
        self.main_splitter.addWidget(self.bottom_tabs)
        
        # Bottom Status Bar
        status_panel = QWidget()
        status_panel.setStyleSheet("background-color: var(--md-sys-color-surface-variant);")
        sp_layout = QHBoxLayout(status_panel)
        sp_layout.setContentsMargins(16, 4, 16, 4)
        
        self.lbl_coord = MaterialLabel("X: 0, Y: 0")
        self.lbl_progress = MaterialLabel("Overall Progress: 0%")
        self.progress_bar = MaterialProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setValue(0)
        
        sp_layout.addWidget(self.lbl_coord)
        sp_layout.addStretch()
        sp_layout.addWidget(self.lbl_progress)
        sp_layout.addWidget(self.progress_bar)
        
        self.layout.addWidget(status_panel)
        
        self.viewer.coordinates_changed.connect(lambda x, y: self.lbl_coord.setText(f"X: {int(x)}, Y: {int(y)}"))
        
    def on_region_selected(self, rect: QRectF):
        self.viewer.add_bounding_box(rect)
        self.log_viewer.append(f"[INFO] Bounding box drawn at: {rect}")
        
    def on_open_image(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open Image(s)", "", "Images (*.png *.jpg *.jpeg *.bmp *.tiff)")
        for path in file_paths:
            self.image_list.addItem(path)
        if file_paths:
            self.load_image(file_paths[0])

    def on_open_pdf_for_ocr(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open PDF for OCR", "", "PDF Files (*.pdf)")
        if not file_path:
            return
        try:
            import fitz
            doc = fitz.open(file_path)
            for i in range(len(doc)):
                self.image_list.addItem(f"{file_path}::page{i + 1}")
            doc.close()
            self.log_viewer.append(f"[INFO] Loaded {file_path} ({len(doc)} pages) for OCR. Select a page from the Images list.")
        except Exception as e:
            self.log_viewer.append(f"[ERROR] Failed to open PDF: {e}")

    def on_image_item_clicked(self, item):
        path = item.text()
        if "::page" in path:
            self.log_viewer.append(f"[WARN] PDF page OCR preview not yet rendered: {path}")
            self.current_image_path = None
            return
        self.load_image(path)

    def load_image(self, path):
        from PySide6.QtGui import QImage
        image = QImage(path)
        if not image.isNull():
            self.viewer.set_image(image)
        self.current_image_path = path
        self.log_viewer.append(f"[INFO] Loaded {os.path.basename(path)}")

    def on_start_ocr(self):
        if not self.current_image_path:
            self.log_viewer.append("[WARN] No image selected. Open an image first.")
            return

        engine_name = self.settings_panel.cb_engine.currentText()
        lang = self.settings_panel.cb_lang.currentText()
        engine_key = engine_name if engine_name in ("tesseract", "easyocr", "paddleocr") else "tesseract"
        self.controller.set_engine(engine_key, lang)

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._start_time = time.time()
        self.progress_bar.setValue(0)
        self.lbl_progress.setText("Overall Progress: 0%")
        self.log_viewer.append(f"[INFO] OCR started ({engine_key}, lang={lang})...")
        self.controller.run_async(self.current_image_path, lang)

    def on_ocr_ready(self, results):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

        text = "<br/>".join(r.text for r in results) if results else ""
        avg_conf = sum(r.confidence for r in results) / len(results) if results else 0.0

        self.result_panel.result_text.setHtml(f"<b>Extracted text:</b><br/>{text}")
        lang = self.settings_panel.cb_lang.currentText()
        self.result_panel.lbl_lang.setText(f"Language: {lang}")
        self.result_panel.lbl_conf.setText(f"Confidence: {avg_conf * 100:.1f}%")

        elapsed = time.time() - self._start_time if self._start_time else 0
        self.stats_panel.update_stats({
            "Total Images": "1",
            "Total Pages": "1",
            "Average Confidence": f"{avg_conf * 100:.1f}%",
            "Elapsed Time": time.strftime("%H:%M:%S", time.gmtime(elapsed)),
            "Estimated Cost": "-",
        }, progress_val=100)
        self.progress_bar.setValue(100)
        self.lbl_progress.setText("Overall Progress: 100%")
        self.log_viewer.append("[INFO] Engine processing complete.")

        self.history.add_history("OCR", {
            "engine": self.settings_panel.cb_engine.currentText(),
            "status": "Completed",
            "duration": time.strftime("%H:%M:%S", time.gmtime(elapsed)),
            "file": os.path.basename(self.current_image_path) if self.current_image_path else "-",
        })

    def on_ocr_failed(self, error_msg):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log_viewer.append(f"[ERROR] OCR failed: {error_msg}")

    def on_stop_ocr(self):
        self.controller.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log_viewer.append("[INFO] OCR stopped by user.")

    def on_save_result(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save OCR Result", "", "Text Files (*.txt)")
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.result_panel.result_text.toPlainText())
        self.log_viewer.append(f"[INFO] Result saved to {file_path}")

    def hideEvent(self, event):
        SettingsManager().settings.ocr_panel_sizes = self.upper_splitter.sizes()
        SettingsManager().save()
        super().hideEvent(event)
