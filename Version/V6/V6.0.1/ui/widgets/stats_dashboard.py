from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout
from ui.widgets.m3_components import MaterialLabel, MaterialProgressBar, MaterialGroupBox
from utils.i18n import tr


class StatsDashboard(QWidget):
    def __init__(self, title=None, stats_dict=None, has_progress=False, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        
        self.form = QFormLayout()
        
        if title:
            self.group = MaterialGroupBox(title)
            self.layout.addWidget(self.group)
            self.form = QFormLayout(self.group)
        else:
            self.layout.addLayout(self.form)
            
        self.labels = {}
        if stats_dict:
            for k, v in stats_dict.items():
                lbl = MaterialLabel(str(v))
                self.labels[k] = lbl
                self.form.addRow(f"{k}:", lbl)
                
        self.progress_bar = None
        if has_progress:
            self.progress_bar = MaterialProgressBar()
            self.progress_bar.setValue(0)
            self.form.addRow(tr("Progress:"), self.progress_bar)
            
        self.layout.addStretch()
        
    def update_stats(self, stats_dict, progress_val=None):
        for k, v in stats_dict.items():
            if k in self.labels:
                self.labels[k].setText(str(v))
        if self.progress_bar is not None and progress_val is not None:
            self.progress_bar.setValue(progress_val)
