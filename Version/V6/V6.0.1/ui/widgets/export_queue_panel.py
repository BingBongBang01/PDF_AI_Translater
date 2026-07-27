from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFormLayout
from ui.widgets.m3_components import MaterialLabel, MaterialProgressBar, MaterialGroupBox

from ui.widgets.material_button import MaterialButton

from ui.widgets.task_queue_table import TaskQueueTable
from ui.widgets.stats_dashboard import StatsDashboard
from utils.i18n import tr
class ExportQueuePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)

        # Queue Table
        g_queue = MaterialGroupBox(tr("Export Queue"))
        l_queue = QVBoxLayout(g_queue)

        self.table = TaskQueueTable(["File", "Format", "Progress", "Status", "ETA"])
        l_queue.addWidget(self.table)

        h_tools = QHBoxLayout()
        self.btn_retry = MaterialButton(tr("Retry"))
        self.btn_cancel = MaterialButton(tr("Cancel"))
        self.btn_pause = MaterialButton(tr("Pause"))
        self.btn_resume = MaterialButton(tr("Resume"))
        self.btn_clear = MaterialButton(tr("Clear Finished"))
        h_tools.addWidget(self.btn_retry)
        h_tools.addWidget(self.btn_cancel)
        h_tools.addWidget(self.btn_pause)
        h_tools.addWidget(self.btn_resume)
        h_tools.addStretch()
        h_tools.addWidget(self.btn_clear)
        l_queue.addLayout(h_tools)

        # Stats
        self.stats = StatsDashboard(tr("Statistics"), {tr("Files"): "0", tr("Pages"): "0", tr("Estimated Size"): "0 MB", tr("Export Time"): "0s", tr("Compression Ratio"): "1:1"}, has_progress=True)

        self.layout.addWidget(g_queue, 3)
        self.layout.addWidget(self.stats, 1)

    def load_mock_queue(self):
        mock_data = [
            ("chapter_1_translated", "PDF", "100%", tr("Completed"), "-"),
            ("contract_v2", "DOCX", "45%", tr("In Progress"), "1m 12s"),
            ("notes_raw", "TXT", "0%", tr("Queued"), "-")
        ]
        self.table.load_data(mock_data)

        self.stats.update_stats({tr("Files"): "3", tr("Pages"): "42", tr("Estimated Size"): "14.5 MB", tr("Export Time"): "4m 20s", tr("Compression Ratio"): "2.1:1"}, progress_val=45)
