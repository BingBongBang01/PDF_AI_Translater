from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog
)
from PySide6.QtCore import Qt
from ui.widgets.m3_components import MaterialLabel, MaterialTabWidget, MaterialSplitter, MaterialMenu

from ui.widgets.material_button import MaterialButton
from ui.widgets.m3_text_field import MaterialTextField
from PySide6.QtGui import QAction

import os

from ui.windows.base_page import BasePage
from ui.widgets.pdf_viewer import PDFViewer
from ui.widgets.thumbnail_list import ThumbnailList
from ui.widgets.bookmark_tree import BookmarkTree
from ui.widgets.page_search import PageSearch
from ui.widgets.pdf_properties_panel import PdfPropertiesPanel
from workers.pdf_worker import ThumbnailWorker, MetadataWorker, PreviewWorker
from models.settings import SettingsManager
from controllers.pdf_controller import PDFController
from utils.i18n import tr

class PDFPage(BasePage):
    def setup_ui(self):
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        self.controller = PDFController(self)
        self.current_pdf = None
        self.current_page_index = 0
        self.total_pages = 0
        self.thumbnail_worker = None
        self.metadata_worker = None
        self.preview_worker = None
        
        self.setAcceptDrops(True)
        
        # --- Top Toolbar ---
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: var(--md-sys-color-surface); border-bottom: 1px solid var(--md-sys-color-outline-variant);")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 8, 16, 8)
        
        self.btn_open = MaterialButton(tr("Open PDF"))
        self.btn_recent = MaterialButton(tr("Recent"))
        self.btn_reload = MaterialButton(tr("Reload"))

        self.btn_zoom_in = MaterialButton(tr("Zoom In"))
        self.btn_zoom_out = MaterialButton(tr("Zoom Out"))
        self.btn_fit = MaterialButton(tr("Fit Width"))
        self.btn_fit_page = MaterialButton(tr("Fit Page"))

        self.btn_prev = MaterialButton(tr("Prev Page"))
        self.btn_next = MaterialButton(tr("Next Page"))

        search_box = MaterialTextField()
        search_box.setPlaceholderText(tr("Search Toolbar..."))
        search_box.setFixedWidth(200)
        search_box.returnPressed.connect(lambda: self.left_tabs.setCurrentWidget(self.page_search) or self.page_search.set_query_and_search(search_box.text()))

        self.btn_open.clicked.connect(self.on_open_clicked)
        self.btn_recent.clicked.connect(self.on_recent_clicked)
        self.btn_reload.clicked.connect(self.on_reload_clicked)
        self.btn_prev.clicked.connect(self.on_prev_page)
        self.btn_next.clicked.connect(self.on_next_page)
        
        for btn in [self.btn_open, self.btn_recent, self.btn_reload, self.btn_zoom_in, self.btn_zoom_out, self.btn_fit, self.btn_fit_page, self.btn_prev, self.btn_next]:
            tb_layout.addWidget(btn)
        tb_layout.addStretch()
        tb_layout.addWidget(search_box)
        self.layout.addWidget(toolbar)
        
        # --- Splitter ---
        self.splitter = MaterialSplitter(Qt.Horizontal)
        self.layout.addWidget(self.splitter, 1)
        
        # Left Panel (Tabs: Thumbnails, Bookmarks, Search)
        self.left_tabs = MaterialTabWidget()
        
        self.thumbnail_list = ThumbnailList()
        self.thumbnail_list.page_selected.connect(self.on_page_selected)
        self.left_tabs.addTab(self.thumbnail_list, tr("Thumbnails"))

        self.bookmark_tree = BookmarkTree()
        self.bookmark_tree.page_selected.connect(self.on_page_selected)
        self.left_tabs.addTab(self.bookmark_tree, tr("Bookmarks"))

        self.page_search = PageSearch()
        self.page_search.search_fn = self.controller.search
        self.page_search.page_selected.connect(self.on_page_selected)
        self.left_tabs.addTab(self.page_search, tr("Search"))
        
        # Center Panel
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self.viewer = PDFViewer()
        self.btn_zoom_in.clicked.connect(self.viewer.zoom_in)
        self.btn_zoom_out.clicked.connect(self.viewer.zoom_out)
        self.btn_fit.clicked.connect(self.viewer.fit_width)
        self.btn_fit_page.clicked.connect(self.viewer.fit_page)
        self.viewer.zoom_changed.connect(self.on_zoom_changed)
        self.viewer.cursor_moved.connect(self.on_cursor_moved)
        self.viewer.page_up_requested.connect(self.on_prev_page)
        self.viewer.page_down_requested.connect(self.on_next_page)
        center_layout.addWidget(self.viewer)
        
        # Right Panel
        self.properties_panel = PdfPropertiesPanel()
        self.properties_panel.btn_ocr.clicked.connect(lambda: self.window().change_page(3))
        self.properties_panel.btn_translate.clicked.connect(self.on_send_to_translate)
        self.properties_panel.btn_export.clicked.connect(lambda: self.window().change_page(4))
        
        self.splitter.addWidget(self.left_tabs)
        self.splitter.addWidget(center_panel)
        self.splitter.addWidget(self.properties_panel)
        
        sizes = SettingsManager().settings.pdf_panel_sizes
        self.splitter.setSizes(sizes)
        
        # --- Bottom Toolbar ---
        bottom_bar = QWidget()
        bottom_bar.setStyleSheet("background-color: var(--md-sys-color-surface); border-top: 1px solid var(--md-sys-color-outline-variant); font-size: 12px;")
        bb_layout = QHBoxLayout(bottom_bar)
        bb_layout.setContentsMargins(16, 4, 16, 4)
        
        self.lbl_status = MaterialLabel(tr("Ready"))
        self.lbl_cursor = MaterialLabel("X: 0, Y: 0")
        self.lbl_zoom = MaterialLabel(tr("Zoom") + ": 100%")
        self.lbl_page_info = MaterialLabel(tr("Page") + ": 0 / 0")
        
        bb_layout.addWidget(self.lbl_status)
        bb_layout.addStretch()
        bb_layout.addWidget(self.lbl_cursor)
        bb_layout.addSpacing(20)
        bb_layout.addWidget(self.lbl_zoom)
        bb_layout.addSpacing(20)
        bb_layout.addWidget(self.lbl_page_info)
        self.layout.addWidget(bottom_bar)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith('.pdf'):
                event.acceptProposedAction()
                
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith('.pdf'):
                self.load_pdf(file_path)

    def on_open_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(self, tr("Open PDF"), "", tr("PDF Files") + " (*.pdf)")
        if file_path:
            self.load_pdf(file_path)

    def on_recent_clicked(self):
        recents = SettingsManager().settings.recent_files
        menu = MaterialMenu(self)
        if not recents:
            action = QAction(tr("(No recent files)"), self)
            action.setEnabled(False)
            menu.addAction(action)
        else:
            for path in recents:
                action = QAction(os.path.basename(path), self)
                action.triggered.connect(lambda checked=False, p=path: self.load_pdf(p))
                menu.addAction(action)
        menu.exec_(self.btn_recent.mapToGlobal(self.btn_recent.rect().bottomLeft()))

    def on_reload_clicked(self):
        if self.current_pdf:
            self.load_pdf(self.current_pdf)

    def _remember_recent(self, file_path):
        settings = SettingsManager().settings
        recents = [p for p in settings.recent_files if p != file_path]
        recents.insert(0, file_path)
        settings.recent_files = recents[:10]
        SettingsManager().save()

    def load_pdf(self, file_path):
        self.current_pdf = file_path
        self.current_page_index = 0
        self.total_pages = 0
        self.lbl_status.setText(f"{tr('Loading')} {os.path.basename(file_path)}...")

        if self.thumbnail_worker:
            self.thumbnail_worker.cancel()

        try:
            self.controller.open(file_path)
        except Exception as e:
            self.lbl_status.setText(f"{tr('Error')}: {e}")
            return

        self._remember_recent(file_path)

        self.metadata_worker = MetadataWorker(file_path, self)
        self.metadata_worker.metadata_ready.connect(self.on_metadata_ready)
        self.metadata_worker.start()

    def on_metadata_ready(self, meta):
        self.properties_panel.set_file_info(meta)

        self.total_pages = meta.get("Page Count", 0)
        self.lbl_page_info.setText(f"{tr('Page')}: 1 / {self.total_pages}")
        self.lbl_status.setText(tr("Ready"))

        self.thumbnail_list.init_pages(self.total_pages)

        self.thumbnail_worker = ThumbnailWorker(self.current_pdf, parent=self)
        self.thumbnail_worker.thumbnail_ready.connect(self.thumbnail_list.set_thumbnail)
        self.thumbnail_worker.start()

        self._load_bookmarks()

        if self.total_pages > 0:
            self.on_page_selected(0)

    def _load_bookmarks(self):
        try:
            bookmarks = self.controller.bookmarks()
        except Exception:
            bookmarks = []
        self.bookmark_tree.load_bookmarks(bookmarks)
            
    def on_page_selected(self, page_index):
        if not self.current_pdf: return
        self.current_page_index = page_index
        self.lbl_page_info.setText(f"{tr('Page')}: {self.current_page_index + 1} / {self.total_pages}")
        
        item = self.thumbnail_list.item(page_index)
        if item:
            self.thumbnail_list.setCurrentItem(item)

        self.preview_worker = PreviewWorker(self.current_pdf, page_index, self.viewer.current_zoom, self)
        self.preview_worker.preview_ready.connect(self.on_preview_ready)
        self.preview_worker.start()

    def on_prev_page(self):
        if self.current_page_index > 0:
            self.on_page_selected(self.current_page_index - 1)
            
    def on_next_page(self):
        if self.current_page_index < self.total_pages - 1:
            self.on_page_selected(self.current_page_index + 1)
        
    def on_preview_ready(self, page_index, image):
        self.viewer.set_image(image)
        
    def on_send_to_translate(self):
        if not self.current_pdf:
            return
        main_win = self.window()
        translate_page = main_win.pages[2]
        translate_page.load_pdf(self.current_pdf, page_index=self.current_page_index)
        main_win.change_page(2)

    def on_zoom_changed(self, zoom):
        self.lbl_zoom.setText(f"{tr('Zoom')}: {int(zoom * 100)}%")
        
    def on_cursor_moved(self, x, y):
        self.lbl_cursor.setText(f"X: {x}, Y: {y}")

    def hideEvent(self, event):
        SettingsManager().settings.pdf_panel_sizes = self.splitter.sizes()
        SettingsManager().save()
        super().hideEvent(event)
