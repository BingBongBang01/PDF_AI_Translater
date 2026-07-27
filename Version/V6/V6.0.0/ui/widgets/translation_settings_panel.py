from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout
from ui.widgets.m3_components import MaterialDoubleSpinBox, MaterialGroupBox, MaterialSpinBox, MaterialScrollArea, MaterialCheckBox

from ui.widgets.m3_combo_box import MaterialComboBox


class TranslationSettingsPanel(MaterialScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("MaterialScrollArea { border: none; background-color: transparent; }")
        
        container = QWidget()
        layout = QVBoxLayout(container)
        
        # Provider & Model
        g1 = MaterialGroupBox(tr("Model Configuration"))
        fl1 = QFormLayout(g1)
        self.cb_provider = MaterialComboBox()
        self.cb_provider.addItems(["Google Gemini", "OpenAI", "Anthropic", "Local Runtime"])
        self.cb_model = MaterialComboBox()
        self.cb_model.addItems(["gemini-2.5-pro", "gpt-4o", "claude-3-5-sonnet"])
        self.cb_src = MaterialComboBox()
        self.cb_src.addItems(["Auto", "English", "Japanese"])
        self.cb_tgt = MaterialComboBox()
        self.cb_tgt.addItems(["Korean", "English"])
        
        fl1.addRow(tr("Provider:"), self.cb_provider)
        fl1.addRow(tr("Model:"), self.cb_model)
        fl1.addRow(tr("Source Lang:"), self.cb_src)
        fl1.addRow(tr("Target Lang:"), self.cb_tgt)
        
        # Parameters
        g2 = MaterialGroupBox(tr("Parameters"))
        fl2 = QFormLayout(g2)
        self.sp_temp = MaterialDoubleSpinBox()
        self.sp_temp.setRange(0, 2)
        self.sp_temp.setSingleStep(0.1)
        self.sp_temp.setValue(0.3)
        self.sp_tokens = MaterialSpinBox()
        self.sp_tokens.setRange(100, 32000)
        self.sp_tokens.setValue(4096)
        self.sp_chunk = MaterialSpinBox()
        self.sp_chunk.setRange(100, 8000)
        self.sp_chunk.setValue(1500)
        self.sp_ctx = MaterialSpinBox()
        self.sp_ctx.setRange(1000, 128000)
        self.sp_ctx.setValue(8000)
        
        fl2.addRow(tr("Temperature:"), self.sp_temp)
        fl2.addRow(tr("Max Tokens:"), self.sp_tokens)
        fl2.addRow(tr("Chunk Size:"), self.sp_chunk)
        fl2.addRow(tr("Context Size:"), self.sp_ctx)
        
        # Execution
        g3 = MaterialGroupBox(tr("Execution"))
        fl3 = QFormLayout(g3)
        self.sp_retry = MaterialSpinBox()
        self.sp_retry.setRange(0, 10)
        self.sp_retry.setValue(3)
        self.chk_streaming = MaterialCheckBox(tr("Enable Streaming"))
        self.chk_streaming.setChecked(True)
        self.chk_tm = MaterialCheckBox(tr("Use Translation Memory"))
        self.chk_tm.setChecked(True)
        
        fl3.addRow(tr("Retry Count:"), self.sp_retry)
        fl3.addRow("", self.chk_streaming)
        fl3.addRow("", self.chk_tm)
        
        layout.addWidget(g1)
        layout.addWidget(g2)
        layout.addWidget(g3)
        layout.addStretch()
        
        self.setWidget(container)
