
from ui.widgets.m3_components import MaterialLabel

from ui.widgets.material_card import MaterialCard

class RecentJobsCard(MaterialCard):
    def __init__(self, title: str = "Recent Jobs", jobs: list = None, parent=None):
        super().__init__(parent)
        
        self.lbl_title = MaterialLabel(title)
        self.lbl_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.layout.addWidget(self.lbl_title)
        
        if not jobs:
            jobs = [
                "14:30 - Started translation of comic_vol1.pdf (Duration: 5m 12s)",
                "12:00 - OCR Extracted invoice_scanned.png (Duration: 12s)"
            ]
            
        for job in jobs:
            lbl = MaterialLabel(job)
            lbl.setStyleSheet("color: var(--md-sys-color-on-surface-variant);")
            self.layout.addWidget(lbl)
            
        self.layout.addStretch()
