from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QHBoxLayout
from ui.widgets.m3_components import MaterialScrollArea, MaterialSpinBox, MaterialGroupBox, MaterialCheckBox

from ui.widgets.m3_combo_box import MaterialComboBox
from ui.widgets.material_button import MaterialButton
from ui.widgets.m3_text_field import MaterialTextField
from utils.i18n import tr


class ExportSettingsPanel(MaterialScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("MaterialScrollArea { border: none; background-color: transparent; }")
        
        container = QWidget()
        layout = QVBoxLayout(container)
        
        # General
        g1 = MaterialGroupBox(tr("General"))
        f1 = QFormLayout(g1)

        h_dest = QHBoxLayout()
        self.le_dest = MaterialTextField()
        self.btn_browse = MaterialButton(tr("Browse"))
        h_dest.addWidget(self.le_dest)
        h_dest.addWidget(self.btn_browse)

        self.le_filename = MaterialTextField()
        self.cb_overwrite = MaterialComboBox(); self.cb_overwrite.addItems([tr("Ask"), tr("Overwrite"), tr("Rename")])
        self.cb_encode = MaterialComboBox(); self.cb_encode.addItems(["UTF-8", "ASCII", "UTF-16"])

        f1.addRow(tr("Output Folder:"), h_dest)
        f1.addRow(tr("File Name:"), self.le_filename)
        f1.addRow(tr("Overwrite Policy:"), self.cb_overwrite)
        f1.addRow(tr("Encoding:"), self.cb_encode)
        layout.addWidget(g1)

        # Document
        g2 = MaterialGroupBox(tr("Document"))
        f2 = QFormLayout(g2)
        self.cb_font = MaterialComboBox(); self.cb_font.addItems(["Arial", "Times New Roman", "Inter"])
        self.sp_size = MaterialSpinBox(); self.sp_size.setRange(8, 72); self.sp_size.setValue(12)
        self.sp_margin = MaterialSpinBox(); self.sp_margin.setRange(0, 100); self.sp_margin.setValue(20)
        self.cb_spacing = MaterialComboBox(); self.cb_spacing.addItems(["1.0", "1.15", "1.5", "2.0"])
        self.chk_header = MaterialCheckBox(tr("Include Header"))
        self.chk_footer = MaterialCheckBox(tr("Include Footer"))

        f2.addRow(tr("Font:"), self.cb_font)
        f2.addRow(tr("Font Size:"), self.sp_size)
        f2.addRow(tr("Margins (px):"), self.sp_margin)
        f2.addRow(tr("Line Spacing:"), self.cb_spacing)
        f2.addRow("", self.chk_header)
        f2.addRow("", self.chk_footer)
        layout.addWidget(g2)

        # Images
        g3 = MaterialGroupBox(tr("Images"))
        f3 = QFormLayout(g3)
        self.sp_dpi = MaterialSpinBox(); self.sp_dpi.setRange(72, 600); self.sp_dpi.setValue(300)
        self.chk_comp = MaterialCheckBox(tr("Enable Image Compression"))
        self.sp_qual = MaterialSpinBox(); self.sp_qual.setRange(10, 100); self.sp_qual.setValue(85)
        f3.addRow(tr("Export DPI:"), self.sp_dpi)
        f3.addRow(tr("JPEG Quality:"), self.sp_qual)
        f3.addRow("", self.chk_comp)
        layout.addWidget(g3)

        # Metadata
        g4 = MaterialGroupBox(tr("Metadata"))
        f4 = QFormLayout(g4)
        self.le_title = MaterialTextField()
        self.le_author = MaterialTextField()
        self.le_sub = MaterialTextField()
        self.le_key = MaterialTextField()
        f4.addRow(tr("Title:"), self.le_title)
        f4.addRow(tr("Author:"), self.le_author)
        f4.addRow(tr("Subject:"), self.le_sub)
        f4.addRow(tr("Keywords:"), self.le_key)
        layout.addWidget(g4)

        # Security
        g5 = MaterialGroupBox(tr("Security"))
        f5 = QFormLayout(g5)
        self.le_pass = MaterialTextField(); self.le_pass.setEchoMode(MaterialTextField.Password)
        self.cb_perm = MaterialComboBox(); self.cb_perm.addItems([tr("Read/Write"), tr("Read-Only")])
        self.cb_enc = MaterialComboBox(); self.cb_enc.addItems(["None", "AES-128", "AES-256"])
        f5.addRow(tr("Password:"), self.le_pass)
        f5.addRow(tr("Permissions:"), self.cb_perm)
        f5.addRow(tr("Encryption:"), self.cb_enc)
        layout.addWidget(g5)

        # Advanced
        g6 = MaterialGroupBox(tr("Advanced"))
        f6 = QFormLayout(g6)
        self.chk_a1 = MaterialCheckBox(tr("Preserve Original Layout"))
        self.chk_a2 = MaterialCheckBox(tr("Merge Output Pages"))
        self.chk_a3 = MaterialCheckBox(tr("Split Output by Chapters"))
        self.chk_a4 = MaterialCheckBox(tr("Include OCR Layer"))
        self.chk_a5 = MaterialCheckBox(tr("Include Translation Output"))
        self.chk_a6 = MaterialCheckBox(tr("Embed Original Metadata"))

        f6.addRow("", self.chk_a1)
        f6.addRow("", self.chk_a2)
        f6.addRow("", self.chk_a3)
        f6.addRow("", self.chk_a4)
        f6.addRow("", self.chk_a5)
        f6.addRow("", self.chk_a6)
        layout.addWidget(g6)
        
        layout.addStretch()
        self.setWidget(container)
