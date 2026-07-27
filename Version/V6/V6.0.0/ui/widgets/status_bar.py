from PySide6.QtWidgets import QStatusBar
from ui.widgets.m3_components import MaterialLabel


class MainStatusBar(QStatusBar):
    """Custom Status Bar with specific sections."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MainStatusBar")
        
        self.lbl_version = MaterialLabel("v6.0.0")
        self.lbl_task = MaterialLabel("Ready")
        self.lbl_gpu = MaterialLabel("GPU: Idle")
        self.lbl_engine = MaterialLabel("Engine: Default")
        
        for lbl in [self.lbl_version, self.lbl_task, self.lbl_gpu, self.lbl_engine]:
            lbl.setProperty('m3_typography', 'label_small')
        
        self.addWidget(self.lbl_version)
        self.addWidget(self.lbl_task, 1)
        self.addPermanentWidget(self.lbl_engine)
        self.addPermanentWidget(self.lbl_gpu)

    def set_status(self, text: str):
        self.lbl_task.setText(text)
        
    def set_gpu_status(self, status: str):
        self.lbl_gpu.setText(f"GPU: {status}")
