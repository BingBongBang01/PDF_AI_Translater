from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt
from ui.widgets.m3_components import MaterialSplitter

from ui.widgets.material_button import MaterialButton
from ui.widgets.m3_text_field import MaterialTextField

import json

from ui.windows.base_page import BasePage
from ui.widgets.history_filter_panel import HistoryFilterPanel
from ui.widgets.task_queue_table import TaskQueueTable
from ui.widgets.history_details_panel import HistoryDetailsPanel
from ui.widgets.stats_dashboard import StatsDashboard
from controllers.history_controller import HistoryController

class HistoryPage(BasePage):
    def setup_ui(self):
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.controller = HistoryController(self)
        self.records = []

        # --- Top Toolbar ---
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: var(--md-sys-color-surface); border-bottom: 1px solid var(--md-sys-color-outline-variant);")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 8, 16, 8)
        
        self.search_box = MaterialTextField()
        self.search_box.setPlaceholderText("Search history...")
        self.search_box.setFixedWidth(300)
        
        self.btn_filter = MaterialButton("Filter")
        self.btn_refresh = MaterialButton("Refresh")
        self.btn_delete = MaterialButton("Delete Selected")
        self.btn_export = MaterialButton("Export History")
        
        self.btn_delete.setStyleSheet("color: var(--md-sys-color-error);")
        
        tb_layout.addWidget(self.search_box)
        tb_layout.addWidget(self.btn_filter)
        tb_layout.addWidget(self.btn_refresh)
        tb_layout.addWidget(self.btn_delete)
        tb_layout.addWidget(self.btn_export)
        tb_layout.addStretch()
        self.layout.addWidget(toolbar)
        
        # --- Main Layout ---
        self.main_v_splitter = MaterialSplitter(Qt.Vertical)
        self.layout.addWidget(self.main_v_splitter, 1)
        
        self.main_h_splitter = MaterialSplitter(Qt.Horizontal)
        
        self.filter_panel = HistoryFilterPanel()

        headers = ["Time", "Project", "File", "Action", "Provider", "Model", "Duration", "Status"]
        self.table = TaskQueueTable(headers)

        self.details_panel = HistoryDetailsPanel()
        
        self.main_h_splitter.addWidget(self.filter_panel)
        self.main_h_splitter.addWidget(self.table)
        self.main_h_splitter.addWidget(self.details_panel)
        
        self.main_h_splitter.setSizes([200, 600, 350])
        
        self.main_v_splitter.addWidget(self.main_h_splitter)
        
        # Bottom Stats
        self.stats_container = QWidget()
        stats_layout = QHBoxLayout(self.stats_container)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stats_volume = StatsDashboard("Volume Statistics", {"Total Projects": "3", "Total Files": "45", "Total Pages": "1,204", "Total Tokens": "2.4M"})
        self.stats_exec = StatsDashboard("Execution Statistics", {"Total OCR Jobs": "32", "Total Translation Jobs": "18", "Average Duration": "42s", "Success Rate": "96.5%"})
        
        stats_layout.addWidget(self.stats_volume)
        stats_layout.addWidget(self.stats_exec)
        
        self.main_v_splitter.addWidget(self.stats_container)
        
        # Connect table selection to details panel
        self.table.itemSelectionChanged.connect(self.on_table_selection)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_delete.clicked.connect(self.on_delete_selected)
        self.btn_export.clicked.connect(self.on_export_history)

        self.refresh()

    def on_show(self):
        self.refresh()

    def refresh(self):
        self.records = self.controller.get_history()
        rows = []
        for r in self.records:
            d = r.get("details", {})
            rows.append((
                r.get("timestamp", "")[:19].replace("T", " "),
                d.get("project", "-"),
                d.get("file", "-"),
                r.get("action", "-"),
                d.get("provider", "-"),
                d.get("model", "-"),
                d.get("duration", "-"),
                d.get("status", "-"),
            ))
        self.table.load_data(rows)

        total_files = len(self.records)
        self.stats_volume.update_stats({
            "Total Projects": str(len({r.get("details", {}).get("project") for r in self.records if r.get("details", {}).get("project")})),
            "Total Files": str(total_files),
            "Total Pages": "-",
            "Total Tokens": "-",
        })
        self.stats_exec.update_stats({
            "Total OCR Jobs": str(sum(1 for r in self.records if r.get("action") == "OCR")),
            "Total Translation Jobs": str(sum(1 for r in self.records if r.get("action") == "Translate")),
            "Average Duration": "-",
            "Success Rate": "-",
        })

    def on_table_selection(self):
        items = self.table.selectedItems()
        if items:
            row = items[0].row()
            if row < len(self.records):
                self.details_panel.load_details(self.records[row])

    def on_delete_selected(self):
        items = self.table.selectedItems()
        if not items:
            return
        rows = sorted({item.row() for item in items}, reverse=True)
        reply = QMessageBox.question(self, "Delete History", f"Delete {len(rows)} record(s)?")
        if reply != QMessageBox.Yes:
            return
        for row in rows:
            if row < len(self.records):
                self.controller.remove_history(self.records[row]["id"])
        self.refresh()

    def on_export_history(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export History", "", "JSON Files (*.json)")
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)
