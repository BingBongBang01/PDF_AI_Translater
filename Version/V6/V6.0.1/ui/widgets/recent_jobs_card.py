
from ui.widgets.m3_components import MaterialLabel

from ui.widgets.material_card import MaterialCard
from utils.i18n import tr

class RecentJobsCard(MaterialCard):
    def __init__(self, title: str = None, jobs: list = None, parent=None):
        super().__init__(parent)
        if title is None:
            title = tr("Recent Jobs")

        self.lbl_title = MaterialLabel(title)
        self.lbl_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.layout.addWidget(self.lbl_title)

        if not jobs:
            jobs = [
                f"14:30 - {tr('Started translation of')} comic_vol1.pdf ({tr('Duration')}: 5m 12s)",
                f"12:00 - {tr('OCR Extracted')} invoice_scanned.png ({tr('Duration')}: 12s)"
            ]
            
        for job in jobs:
            lbl = MaterialLabel(job)
            lbl.setStyleSheet("color: var(--md-sys-color-on-surface-variant);")
            self.layout.addWidget(lbl)
            
        self.layout.addStretch()
