from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog
)
from PySide6.QtCore import Qt
from ui.widgets.m3_components import MaterialSplitter

from ui.widgets.material_button import MaterialButton

import os

from ui.windows.base_page import BasePage
from ui.widgets.export_targets_panel import ExportTargetsPanel
from ui.widgets.export_preview_panel import ExportPreviewPanel
from ui.widgets.export_settings_panel import ExportSettingsPanel
from ui.widgets.export_queue_panel import ExportQueuePanel
from controllers.export_controller import ExportController

class ExportPage(BasePage):
    def setup_ui(self):
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.controller = ExportController(self)
        self.controller.task_finished.connect(self.on_task_finished)
        self.source_path = None
        self._jobs = []  # list of dicts for queue table rendering

        # --- Top Toolbar ---
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: var(--md-sys-color-surface); border-bottom: 1px solid var(--md-sys-color-outline-variant);")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 8, 16, 8)
        
        self.btn_export = MaterialButton("Export")
        self.btn_export.setStyleSheet("background-color: var(--md-sys-color-primary); color: var(--md-sys-color-on-primary); font-weight: bold;")
        self.btn_preview = MaterialButton("Preview")
        self.btn_save_preset = MaterialButton("Save Preset")
        self.btn_load_preset = MaterialButton("Load Preset")
        self.btn_reset = MaterialButton("Reset")
        
        for btn in [self.btn_export, self.btn_preview, self.btn_save_preset, self.btn_load_preset, self.btn_reset]:
            tb_layout.addWidget(btn)
        tb_layout.addStretch()
        self.layout.addWidget(toolbar)
        
        # --- Main Layout ---
        self.main_v_splitter = MaterialSplitter(Qt.Vertical)
        self.layout.addWidget(self.main_v_splitter, 1)
        
        self.main_h_splitter = MaterialSplitter(Qt.Horizontal)
        
        self.targets_panel = ExportTargetsPanel()
        self.preview_panel = ExportPreviewPanel()
        self.settings_panel = ExportSettingsPanel()
        
        self.main_h_splitter.addWidget(self.targets_panel)
        self.main_h_splitter.addWidget(self.preview_panel)
        self.main_h_splitter.addWidget(self.settings_panel)
        
        self.main_h_splitter.setSizes([200, 500, 400])
        self.main_v_splitter.addWidget(self.main_h_splitter)
        
        # Bottom Layout
        self.queue_panel = ExportQueuePanel()
        self.main_v_splitter.addWidget(self.queue_panel)
        self.main_v_splitter.setSizes([700, 300])
        
        self.settings_panel.btn_browse.clicked.connect(self.on_browse_folder)

        # Connect Selection
        self.targets_panel.target_list.itemSelectionChanged.connect(self.on_target_selection)
        self.btn_export.clicked.connect(self.on_export_clicked)

    def on_target_selection(self):
        items = self.targets_panel.target_list.selectedItems()
        if items:
            format_name = items[0].text()
            self.preview_panel.load_mock_preview(format_name)

    def on_browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.settings_panel.le_dest.setText(folder)

    def on_export_clicked(self):
        items = self.targets_panel.target_list.selectedItems()
        if not items:
            return
        target_label = items[0].text()

        source_path, _ = QFileDialog.getOpenFileName(self, "Select Source File to Export", "", "All Files (*.*)")
        if not source_path:
            return

        destination_folder = self.settings_panel.le_dest.text().strip()
        if not destination_folder:
            destination_folder = os.path.dirname(source_path)
            self.settings_panel.le_dest.setText(destination_folder)

        options = {
            "overwrite": self.settings_panel.cb_overwrite.currentText() == "Overwrite",
            "compress": self.settings_panel.chk_comp.isChecked(),
            "include_metadata": True,
        }

        task = self.controller.export_file(source_path, target_label, destination_folder, options)

        self._jobs.append({"name": task.document_id, "format": target_label.split("(")[0].strip(), "status": "In Progress", "eta": "-"})
        self._refresh_queue()

    def on_task_finished(self, document_id, success, message):
        for job in self._jobs:
            if job["name"] == document_id and job["status"] == "In Progress":
                job["status"] = "Completed" if success else "Failed"
                job["message"] = message
                break
        self._refresh_queue()

    def _refresh_queue(self):
        rows = [
            (j["name"], j["format"], "100%" if j["status"] != "In Progress" else "...", j["status"], j.get("eta", "-"))
            for j in self._jobs
        ]
        self.queue_panel.table.load_data(rows)
        completed = sum(1 for j in self._jobs if j["status"] == "Completed")
        self.queue_panel.stats.update_stats({
            "Files": str(len(self._jobs)),
            "Pages": "-",
            "Estimated Size": "-",
            "Export Time": "-",
            "Compression Ratio": "-",
        }, progress_val=int(completed / len(self._jobs) * 100) if self._jobs else 0)
