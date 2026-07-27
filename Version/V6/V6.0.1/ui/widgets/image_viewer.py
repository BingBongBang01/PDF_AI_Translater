from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPixmap, QWheelEvent, QPen, QColor, QPainter

class ImageViewer(QGraphicsView):
    """Custom GraphicsView for OCR image preview with region selection and bounding boxes."""
    zoom_changed = Signal(float)
    coordinates_changed = Signal(float, float)
    region_selected = Signal(QRectF)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, True)
        self.setMouseTracking(True)
        
        self.current_zoom = 1.0
        self.pixmap_item = None
        self.selection_rect = None
        self.start_pos = None
        self.mode = "pan" # 'pan' or 'select'
        
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
        
    def set_mode(self, mode):
        self.mode = mode
        if mode == "pan":
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        else:
            self.setDragMode(QGraphicsView.NoDrag)
            
    def mousePressEvent(self, event):
        if self.mode == "select" and event.button() == Qt.LeftButton:
            self.start_pos = self.mapToScene(event.pos())
            if self.selection_rect:
                self.scene.removeItem(self.selection_rect)
            self.selection_rect = QGraphicsRectItem(QRectF(self.start_pos, self.start_pos))
            pen = QPen(QColor(255, 0, 0))
            pen.setWidth(2)
            self.selection_rect.setPen(pen)
            self.scene.addItem(self.selection_rect)
        else:
            super().mousePressEvent(event)
            
    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        self.coordinates_changed.emit(scene_pos.x(), scene_pos.y())
        
        if self.mode == "select" and self.start_pos:
            rect = QRectF(self.start_pos, scene_pos).normalized()
            if self.selection_rect:
                self.selection_rect.setRect(rect)
        else:
            super().mouseMoveEvent(event)
            
    def mouseReleaseEvent(self, event):
        if self.mode == "select" and event.button() == Qt.LeftButton and self.start_pos:
            scene_pos = self.mapToScene(event.pos())
            rect = QRectF(self.start_pos, scene_pos).normalized()
            if rect.width() > 5 and rect.height() > 5:
                self.region_selected.emit(rect)
            self.start_pos = None
        else:
            super().mouseReleaseEvent(event)
            
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)
            
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
                
    def add_bounding_box(self, rect: QRectF, color=QColor(0, 255, 0)):
        box = QGraphicsRectItem(rect)
        pen = QPen(color)
        pen.setWidth(2)
        box.setPen(pen)
        self.scene.addItem(box)
