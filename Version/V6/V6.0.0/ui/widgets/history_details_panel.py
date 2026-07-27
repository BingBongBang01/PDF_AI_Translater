from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFormLayout
from ui.widgets.m3_components import MaterialLabel, MaterialGroupBox

from ui.widgets.material_button import MaterialButton


class HistoryDetailsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        
        # Details Form
        g_details = MaterialGroupBox("Job Details")
        self.form = QFormLayout(g_details)
        
        self.lbl_src = MaterialLabel("--")
        self.lbl_out = MaterialLabel("--")
        self.lbl_pages = MaterialLabel("--")
        self.lbl_chunks = MaterialLabel("--")
        self.lbl_prov = MaterialLabel("--")
        self.lbl_mod = MaterialLabel("--")
        self.lbl_eng = MaterialLabel("--")
        self.lbl_fmt = MaterialLabel("--")
        self.lbl_dur = MaterialLabel("--")
        self.lbl_tok = MaterialLabel("--")
        self.lbl_cost = MaterialLabel("--")
        self.lbl_stat = MaterialLabel("--")
        self.lbl_err = MaterialLabel("--")
        self.lbl_err.setStyleSheet("color: var(--md-sys-color-error);")
        
        self.form.addRow("Source File:", self.lbl_src)
        self.form.addRow("Output File:", self.lbl_out)
        self.form.addRow("Pages:", self.lbl_pages)
        self.form.addRow("Chunks:", self.lbl_chunks)
        self.form.addRow("Provider:", self.lbl_prov)
        self.form.addRow("Model:", self.lbl_mod)
        self.form.addRow("OCR Engine:", self.lbl_eng)
        self.form.addRow("Export Format:", self.lbl_fmt)
        self.form.addRow("Duration:", self.lbl_dur)
        self.form.addRow("Tokens:", self.lbl_tok)
        self.form.addRow("Estimated Cost:", self.lbl_cost)
        self.form.addRow("Status:", self.lbl_stat)
        self.form.addRow("Error Message:", self.lbl_err)
        
        self.layout.addWidget(g_details)
        
        # Actions
        g_actions = MaterialGroupBox("Actions")
        v_actions = QVBoxLayout(g_actions)
        
        h1 = QHBoxLayout()
        self.btn_open_proj = MaterialButton("Open Project")
        self.btn_open_fold = MaterialButton("Open Folder")
        h1.addWidget(self.btn_open_proj)
        h1.addWidget(self.btn_open_fold)
        
        h2 = QHBoxLayout()
        self.btn_retry = MaterialButton("Retry")
        self.btn_dup = MaterialButton("Duplicate")
        h2.addWidget(self.btn_retry)
        h2.addWidget(self.btn_dup)
        
        h3 = QHBoxLayout()
        self.btn_export_log = MaterialButton("Export Log")
        self.btn_delete = MaterialButton("Delete")
        self.btn_delete.setStyleSheet("background-color: var(--md-sys-color-error); color: var(--md-sys-color-on-error);")
        h3.addWidget(self.btn_export_log)
        h3.addWidget(self.btn_delete)
        
        v_actions.addLayout(h1)
        v_actions.addLayout(h2)
        v_actions.addLayout(h3)
        
        self.layout.addWidget(g_actions)
        self.layout.addStretch()
        
    def load_details(self, record: dict):
        details = record.get("details", {})
        self.lbl_src.setText(str(details.get("source", "--")))
        self.lbl_out.setText(str(details.get("output", "--")))
        self.lbl_pages.setText(str(details.get("pages", "--")))
        self.lbl_chunks.setText(str(details.get("chunks", "--")))
        self.lbl_prov.setText(str(details.get("provider", "--")))
        self.lbl_mod.setText(str(details.get("model", "--")))
        self.lbl_eng.setText(str(details.get("engine", "--")))
        self.lbl_fmt.setText(str(details.get("format", "--")))
        self.lbl_dur.setText(str(details.get("duration", "--")))
        self.lbl_tok.setText(str(details.get("tokens", "--")))
        self.lbl_cost.setText(str(details.get("cost", "--")))
        self.lbl_stat.setText(str(details.get("status", record.get("action", "--"))))
        self.lbl_err.setText(str(details.get("error", "None")))

    def load_mock_details(self, action_type):
        if action_type == "Translate":
            self.lbl_src.setText("chapter_1.pdf")
            self.lbl_out.setText("chapter_1_translated.pdf")
            self.lbl_pages.setText("24")
            self.lbl_chunks.setText("120")
            self.lbl_prov.setText("Google Gemini")
            self.lbl_mod.setText("gemini-2.5-pro")
            self.lbl_eng.setText("N/A")
            self.lbl_fmt.setText("PDF")
            self.lbl_dur.setText("45s")
            self.lbl_tok.setText("45,200")
            self.lbl_cost.setText("$0.45")
            self.lbl_stat.setText("Completed")
            self.lbl_err.setText("None")
        else:
            self.lbl_src.setText("contract_v2.pdf")
            self.lbl_out.setText("contract_v2_ocr.txt")
            self.lbl_pages.setText("12")
            self.lbl_chunks.setText("N/A")
            self.lbl_prov.setText("N/A")
            self.lbl_mod.setText("N/A")
            self.lbl_eng.setText("Tesseract")
            self.lbl_fmt.setText("TXT")
            self.lbl_dur.setText("1m 20s")
            self.lbl_tok.setText("N/A")
            self.lbl_cost.setText("N/A")
            self.lbl_stat.setText("Completed")
            self.lbl_err.setText("None")
