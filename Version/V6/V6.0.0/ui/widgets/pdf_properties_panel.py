from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout
from ui.widgets.material_card import MaterialCard
from PySide6.QtCore import Qt
from ui.widgets.m3_components import MaterialScrollArea, MaterialLabel, MaterialCheckBox

from ui.widgets.m3_combo_box import MaterialComboBox
from ui.widgets.material_button import MaterialButton


class PdfPropertiesPanel(MaterialScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("MaterialScrollArea { border: none; background-color: transparent; }")
        
        container = QWidget()
        self.layout = QVBoxLayout(container)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(16)
        
        # 1. File Information
        self.info_card = MaterialCard()
        self.info_layout = QFormLayout(self.info_card)
        self.layout.addWidget(MaterialLabel("<b>File Information</b>"))
        self.layout.addWidget(self.info_card)
        
        # 2. Properties
        self.prop_card = MaterialCard()
        prop_layout = QFormLayout(self.prop_card)
        prop_layout.addRow("PDF Version:", MaterialLabel("1.7"))
        prop_layout.addRow("Fast Web View:", MaterialLabel("Yes"))
        prop_layout.addRow("Security:", MaterialLabel("None"))
        self.layout.addWidget(MaterialLabel("<b>Properties</b>"))
        self.layout.addWidget(self.prop_card)
        
        # 3. Output Settings / Hooks
        self.out_card = MaterialCard()
        out_layout = QVBoxLayout(self.out_card)
        
        form = QFormLayout()
        form.addRow("Target Language:", MaterialComboBox())
        form.addRow("OCR Quality:", MaterialComboBox())
        form.addRow("Preserve Formatting:", MaterialCheckBox())
        out_layout.addLayout(form)
        
        btn_layout = QVBoxLayout()
        self.btn_ocr = MaterialButton("Run OCR")
        self.btn_translate = MaterialButton("Send to Translation")
        self.btn_export = MaterialButton("Export Document")
        
        btn_layout.addWidget(self.btn_ocr)
        btn_layout.addWidget(self.btn_translate)
        btn_layout.addWidget(self.btn_export)
        out_layout.addLayout(btn_layout)
        
        self.layout.addWidget(MaterialLabel("<b>Output & Tools</b>"))
        self.layout.addWidget(self.out_card)
        
        self.layout.addStretch()
        self.setWidget(container)
        
    def set_file_info(self, info_dict):
        while self.info_layout.count():
            item = self.info_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        for k, v in info_dict.items():
            self.info_layout.addRow(str(k), MaterialLabel(str(v)))
