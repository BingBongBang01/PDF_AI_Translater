from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout
from ui.widgets.m3_components import MaterialDoubleSpinBox, MaterialGroupBox, MaterialSpinBox, MaterialScrollArea, MaterialCheckBox

from ui.widgets.m3_combo_box import MaterialComboBox


class OcrSettingsPanel(MaterialScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("MaterialScrollArea { border: none; background-color: transparent; }")
        
        container = QWidget()
        layout = QVBoxLayout(container)
        
        # Engine Config
        g1 = MaterialGroupBox("Engine")
        fl1 = QFormLayout(g1)
        self.cb_engine = MaterialComboBox()
        self.cb_engine.addItems(["tesseract", "manga-ocr"])
        self.cb_lang = MaterialComboBox()
        self.cb_lang.addItems(["eng", "jpn", "kor"])
        self.sp_dpi = MaterialSpinBox()
        self.sp_dpi.setRange(72, 600)
        self.sp_dpi.setValue(300)
        
        fl1.addRow("OCR Engine:", self.cb_engine)
        fl1.addRow("Language:", self.cb_lang)
        fl1.addRow("Target DPI:", self.sp_dpi)
        
        # Preprocessing
        g2 = MaterialGroupBox("Preprocessing")
        fl2 = QFormLayout(g2)
        self.chk_rotate = MaterialCheckBox("Auto Rotate")
        self.chk_rotate.setChecked(True)
        self.chk_deskew = MaterialCheckBox("Deskew")
        self.chk_denoise = MaterialCheckBox("Denoise")
        self.chk_thresh = MaterialCheckBox("Binarization")
        
        fl2.addRow("", self.chk_rotate)
        fl2.addRow("", self.chk_deskew)
        fl2.addRow("", self.chk_denoise)
        fl2.addRow("", self.chk_thresh)
        
        # Execution
        g3 = MaterialGroupBox("Execution")
        fl3 = QFormLayout(g3)
        self.sp_conf = MaterialDoubleSpinBox()
        self.sp_conf.setRange(0.0, 1.0)
        self.sp_conf.setSingleStep(0.1)
        self.sp_conf.setValue(0.5)
        
        fl3.addRow("Confidence Threshold:", self.sp_conf)
        
        layout.addWidget(g1)
        layout.addWidget(g2)
        layout.addWidget(g3)
        layout.addStretch()
        
        self.setWidget(container)
