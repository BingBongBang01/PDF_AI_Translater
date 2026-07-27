from PySide6.QtWidgets import QWidget, QVBoxLayout
from ui.widgets.m3_components import MaterialRadioButton, MaterialGroupBox, MaterialListWidget, MaterialCheckBox
from utils.i18n import tr


class HistoryFilterPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)

        # Date Filter
        g1 = MaterialGroupBox(tr("Date Filter"))
        l1 = QVBoxLayout(g1)
        self.rb_today = MaterialRadioButton(tr("Today"))
        self.rb_yest = MaterialRadioButton(tr("Yesterday"))
        self.rb_week = MaterialRadioButton(tr("Last 7 Days"))
        self.rb_month = MaterialRadioButton(tr("Last Month"))
        self.rb_all = MaterialRadioButton(tr("All Time"))
        self.rb_all.setChecked(True)
        l1.addWidget(self.rb_today)
        l1.addWidget(self.rb_yest)
        l1.addWidget(self.rb_week)
        l1.addWidget(self.rb_month)
        l1.addWidget(self.rb_all)
        self.layout.addWidget(g1)

        # Project Filter
        g2 = MaterialGroupBox(tr("Project Filter"))
        l2 = QVBoxLayout(g2)
        self.project_list = MaterialListWidget()
        self.project_list.addItems([tr("All Projects"), tr("Manga Scanlation"), tr("Legal Docs"), tr("Technical Manuals")])
        self.project_list.setCurrentRow(0)
        l2.addWidget(self.project_list)
        self.layout.addWidget(g2)

        # Status Filter
        g3 = MaterialGroupBox(tr("Status Filter"))
        l3 = QVBoxLayout(g3)
        self.chk_comp = MaterialCheckBox(tr("Completed"))
        self.chk_comp.setChecked(True)
        self.chk_fail = MaterialCheckBox(tr("Failed"))
        self.chk_fail.setChecked(True)
        self.chk_prog = MaterialCheckBox(tr("In Progress"))
        self.chk_prog.setChecked(True)
        l3.addWidget(self.chk_comp)
        l3.addWidget(self.chk_fail)
        l3.addWidget(self.chk_prog)
        self.layout.addWidget(g3)
        
        self.layout.addStretch()
