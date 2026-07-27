from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QWheelEvent, QAction, QPainter
from ui.widgets.m3_components import MaterialMenu


class PDFViewer(QGraphicsView):
    """Custom GraphicsView for displaying high-resolution PDFs with panning and zooming."""
    zoom_changed = Signal(float)
    cursor_moved = Signal(int, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False) # For speed
        self.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, True)
        
        self.current_zoom = 1.0
        self.pixmap_item = None
        
        # Enable mouse tracking to emit cursor position
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        
        self.setStyleSheet("""
            QGraphicsView {
                background-color: var(--md-sys-color-surface-container);
                border: none;
            }
        """)
        
    def set_image(self, image):
        self.scene.clear()
        pixmap = QPixmap.fromImage(image)
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)
            
    def mouseMoveEvent(self, event):
        pos = self.mapToScene(event.pos())
        self.cursor_moved.emit(int(pos.x()), int(pos.y()))
        super().mouseMoveEvent(event)
        
    def contextMenuEvent(self, event):
        menu = MaterialMenu(self)
        copy_action = QAction("Copy", self)
        highlight_action = QAction("Highlight", self)
        translate_action = QAction("Send to Translation", self)
        
        menu.addAction(copy_action)
        menu.addAction(highlight_action)
        menu.addSeparator()
        menu.addAction(translate_action)
        
        menu.exec_(event.globalPos())
            
    def zoom_in(self):
        self.scale(1.2, 1.2)
        self.current_zoom *= 1.2
        self.zoom_changed.emit(self.current_zoom)
        
    def zoom_out(self):
        self.scale(1.0/1.2, 1.0/1.2)
        self.current_zoom /= 1.2
        self.zoom_changed.emit(self.current_zoom)
        
    def fit_width(self):
        if self.pixmap_item:
            view_width = self.viewport().width()
            img_width = self.pixmap_item.boundingRect().width()
            if img_width > 0:
                factor = view_width / img_width
                self.resetTransform()
                self.scale(factor, factor)
                self.current_zoom = factor
                self.zoom_changed.emit(factor)

    def fit_page(self):
        if self.pixmap_item:
            view_rect = self.viewport().rect()
            img_rect = self.pixmap_item.boundingRect()
            if img_rect.width() > 0 and img_rect.height() > 0:
                factor_w = view_rect.width() / img_rect.width()
                factor_h = view_rect.height() / img_rect.height()
                factor = min(factor_w, factor_h)
                self.resetTransform()
                self.scale(factor, factor)
                self.current_zoom = factor
                self.zoom_changed.emit(factor)
