from PySide6.QtWidgets import (
    QToolButton, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox,
    QSlider, QCheckBox, QRadioButton, QGroupBox, QFrame, QTabWidget,
    QTreeWidget, QTreeView, QTableWidget, QTableView, QListWidget,
    QListView, QMenu, QMenuBar, QToolBar, QStatusBar, QDockWidget,
    QProgressBar, QSplitter, QScrollArea, QScrollBar, QLabel, QApplication
)
from PySide6.QtCore import Qt

def _apply_global_m3_styles():
    """Helper to get M3 Design System tokens."""
    app = QApplication.instance()
    ds = app.property("m3_design_system") if app else None
    return ds

class MaterialToolButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty('m3_typography', 'label_medium')
        ds = _apply_global_m3_styles()
        if ds:
            self.setStyleSheet(f"QToolButton {{ background-color: transparent; border-radius: {ds.shape.small}; padding: 4px; }} QToolButton:hover {{ background-color: {ds.colors.hover}; }}")

class MaterialPlainTextEdit(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty('m3_typography', 'body_large')

class MaterialTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty('m3_typography', 'body_large')

class MaterialSpinBox(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty('m3_typography', 'body_large')

class MaterialDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty('m3_typography', 'body_large')

class MaterialSlider(QSlider):
    def __init__(self, parent=None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

class MaterialCheckBox(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setProperty('m3_typography', 'body_medium')

class MaterialRadioButton(QRadioButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setProperty('m3_typography', 'body_medium')

class MaterialGroupBox(QGroupBox):
    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self.setProperty('m3_typography', 'title_medium')

class MaterialFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

class MaterialTabWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

class MaterialTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

class MaterialTreeView(QTreeView):
    def __init__(self, parent=None):
        super().__init__(parent)

class MaterialTableWidget(QTableWidget):
    def __init__(self, *args):
        super().__init__(*args)

class MaterialTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)

class MaterialListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

class MaterialListView(QListView):
    def __init__(self, parent=None):
        super().__init__(parent)

class MaterialMenu(QMenu):
    def __init__(self, title="", parent=None):
        super().__init__(title, parent)

class MaterialMenuBar(QMenuBar):
    def __init__(self, parent=None):
        super().__init__(parent)

class MaterialToolBar(QToolBar):
    def __init__(self, title="", parent=None):
        super().__init__(title, parent)

class MaterialDockWidget(QDockWidget):
    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self.setProperty('m3_typography', 'title_medium')

class MaterialProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)

class MaterialSplitter(QSplitter):
    def __init__(self, parent=None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

class MaterialScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)

class MaterialScrollBar(QScrollBar):
    def __init__(self, parent=None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

class MaterialLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setProperty('m3_typography', 'body_medium')
        self.setWordWrap(True)
