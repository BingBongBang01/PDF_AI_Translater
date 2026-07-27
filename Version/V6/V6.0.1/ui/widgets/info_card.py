from PySide6.QtWidgets import QGridLayout
from ui.widgets.m3_components import MaterialLabel

from ui.widgets.material_card import MaterialCard

class InfoCard(MaterialCard):
    def __init__(self, title: str, info_dict: dict, parent=None):
        super().__init__(parent)
        
        self.lbl_title = MaterialLabel(title)
        self.lbl_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.layout.addWidget(self.lbl_title)
        
        self.grid = QGridLayout()
        for i, (k, v) in enumerate(info_dict.items()):
            self.grid.addWidget(MaterialLabel(f"{k}:"), i, 0)
            v_lbl = MaterialLabel(str(v))
            v_lbl.setWordWrap(True)
            v_lbl.setStyleSheet("color: var(--md-sys-color-primary);")
            self.grid.addWidget(v_lbl, i, 1)
            
        self.layout.addLayout(self.grid)
        self.layout.addStretch()
