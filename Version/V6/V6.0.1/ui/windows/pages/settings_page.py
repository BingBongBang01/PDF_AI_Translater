from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QFormLayout
)
from PySide6.QtCore import Qt
from ui.widgets.m3_components import MaterialLabel, MaterialDoubleSpinBox, MaterialSplitter, MaterialSpinBox, MaterialScrollArea, MaterialGroupBox, MaterialListWidget, MaterialCheckBox

from ui.widgets.m3_combo_box import MaterialComboBox
from ui.widgets.material_button import MaterialButton
from ui.widgets.m3_text_field import MaterialTextField


from ui.windows.base_page import BasePage
from models.settings import SettingsManager
from ui.themes.theme_manager import ThemeManager
from utils.i18n import tr

class SettingsPage(BasePage):
    def setup_ui(self):
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Splitter for sidebar and content
        self.splitter = MaterialSplitter(Qt.Horizontal)
        self.layout.addWidget(self.splitter, 1)
        
        # Sidebar Navigation
        self.nav_list = MaterialListWidget()
        self.nav_list.setFixedWidth(200)
        self.nav_list.setStyleSheet("""
            MaterialListWidget {
                background-color: var(--md-sys-color-surface);
                border-right: 1px solid var(--md-sys-color-outline-variant);
                font-size: 14px;
            }
            MaterialListWidget::item {
                padding: 12px 16px;
                border-radius: 8px;
                margin: 4px 8px;
            }
            MaterialListWidget::item:selected {
                background-color: var(--md-sys-color-primary-container);
                color: var(--md-sys-color-on-primary-container);
                font-weight: bold;
            }
        """)
        
        categories = [
            tr("General"), tr("Appearance"), tr("Translation"), tr("OCR"), tr("PDF"), 
            tr("Export"), tr("Performance"), tr("Network"), tr("Storage"), tr("Updates"), 
            tr("Advanced"), tr("About")
        ]
        self.nav_list.addItems(categories)
        self.nav_list.currentRowChanged.connect(self.on_category_changed)
        
        # Stacked Content Area
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_general())
        self.content_stack.addWidget(self._build_appearance())
        self.content_stack.addWidget(self._build_translation())
        self.content_stack.addWidget(self._build_ocr())
        self.content_stack.addWidget(self._build_pdf())
        self.content_stack.addWidget(self._build_export())
        self.content_stack.addWidget(self._build_performance())
        self.content_stack.addWidget(self._build_network())
        self.content_stack.addWidget(self._build_storage())
        self.content_stack.addWidget(self._build_updates())
        self.content_stack.addWidget(self._build_advanced())
        self.content_stack.addWidget(self._build_about())
        
        self.splitter.addWidget(self.nav_list)
        self.splitter.addWidget(self.content_stack)
        
        self.nav_list.setCurrentRow(0)
        
    def on_category_changed(self, index):
        self.content_stack.setCurrentIndex(index)
        
    def _create_scroll_panel(self, build_func):
        scroll = MaterialScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("MaterialScrollArea { border: none; background-color: transparent; }")
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        build_func(layout)
        
        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _build_general(self):
        def builder(layout):
            g = MaterialGroupBox(tr("General Options"))
            f = QFormLayout(g)
            from PySide6.QtWidgets import QMessageBox
            self.cb_lang = MaterialComboBox(); self.cb_lang.addItems(["English", "Korean", "Japanese"])
            self.cb_lang.setCurrentText(SettingsManager().settings.ui_language)
            
            def apply_language(lang):
                if SettingsManager().settings.ui_language != lang:
                    SettingsManager().settings.ui_language = lang
                    SettingsManager().save()
                    QMessageBox.information(self, "Language Changed", "Please restart the application to fully apply the language changes.")
                    
            self.cb_lang.currentTextChanged.connect(apply_language)
            
            self.cb_startup = MaterialComboBox(); self.cb_startup.addItems(["Open Last File", "Show Home Page"])
            self.chk_autosave = MaterialCheckBox("Enable Auto Save")
            self.chk_autorecover = MaterialCheckBox("Enable Auto Recovery")
            self.sp_recent = MaterialSpinBox(); self.sp_recent.setRange(0, 50)
            
            f.addRow("Language:", self.cb_lang)
            f.addRow("Startup Behavior:", self.cb_startup)
            f.addRow("Recent Files Limit:", self.sp_recent)
            f.addRow("", self.chk_autosave)
            f.addRow("", self.chk_autorecover)
            layout.addWidget(g)
        return self._create_scroll_panel(builder)
        
    def _build_appearance(self):
        def builder(layout):
            g = MaterialGroupBox("Appearance Options")
            f = QFormLayout(g)
            self.cb_theme = MaterialComboBox()
            self.cb_theme.addItems(["system", "light", "dark"])
            
            # Immediately toggle theme
            self.cb_theme.currentTextChanged.connect(self._apply_theme)
            
            self.cb_accent = MaterialComboBox(); self.cb_accent.addItems(["Blue", "Green", "Purple", "Orange"])
            self.sp_fontsize = MaterialSpinBox(); self.sp_fontsize.setRange(8, 24); self.sp_fontsize.setValue(10)
            self.cb_scale = MaterialComboBox(); self.cb_scale.addItems(["100%", "125%", "150%", "200%"])
            self.chk_animations = MaterialCheckBox("Enable UI Animations")
            self.chk_animations.setChecked(True)
            self.chk_sys_theme = MaterialCheckBox("Sync with System Theme")
            
            f.addRow("Theme:", self.cb_theme)
            f.addRow("Accent Color:", self.cb_accent)
            f.addRow("Font Size (px):", self.sp_fontsize)
            f.addRow("UI Scale:", self.cb_scale)
            f.addRow("", self.chk_animations)
            f.addRow("", self.chk_sys_theme)
            
            layout.addWidget(g)
            
            s = SettingsManager().settings
            self.cb_theme.setCurrentText(s.theme)
        return self._create_scroll_panel(builder)
        
    def _apply_theme(self, theme_name):
        # Apply changes immediately
        ThemeManager.apply_theme(self.window(), theme_name)
        SettingsManager().settings.theme = theme_name
        
    def _build_translation(self):
        def builder(layout):
            g = MaterialGroupBox("Translation Configuration")
            f = QFormLayout(g)
            self.cb_t_prov = MaterialComboBox(); self.cb_t_prov.addItems(["Google Gemini", "OpenAI", "Anthropic", "Local Runtime"])
            self.cb_t_mod = MaterialComboBox()
            
            def update_model_list(provider: str):
                self.cb_t_mod.clear()
                if provider == "Google Gemini":
                    self.cb_t_mod.addItems(["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro"])
                elif provider == "OpenAI":
                    self.cb_t_mod.addItems(["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"])
                elif provider == "Anthropic":
                    self.cb_t_mod.addItems(["claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku"])
                else:
                    self.cb_t_mod.addItems(["llama-3-8b", "gemma-2-9b"])
                    
            self.cb_t_prov.currentTextChanged.connect(update_model_list)
            update_model_list("Google Gemini")
            self.sp_t_temp = MaterialDoubleSpinBox(); self.sp_t_temp.setRange(0, 2); self.sp_t_temp.setSingleStep(0.1)
            self.sp_t_topp = MaterialDoubleSpinBox(); self.sp_t_topp.setRange(0, 1); self.sp_t_topp.setSingleStep(0.1)
            self.sp_t_max = MaterialSpinBox(); self.sp_t_max.setRange(100, 32000); self.sp_t_max.setSingleStep(100)
            self.sp_t_chunk = MaterialSpinBox(); self.sp_t_chunk.setRange(100, 8000)
            self.chk_t_stream = MaterialCheckBox("Enable Streaming")
            self.sp_t_retry = MaterialSpinBox(); self.sp_t_retry.setRange(0, 10)
            self.sp_t_timeout = MaterialSpinBox(); self.sp_t_timeout.setRange(10, 300)
            self.chk_t_mem = MaterialCheckBox("Use Translation Memory")
            
            f.addRow("Provider:", self.cb_t_prov)
            f.addRow("Model:", self.cb_t_mod)
            f.addRow("Temperature:", self.sp_t_temp)
            f.addRow("Top P:", self.sp_t_topp)
            f.addRow("Max Tokens:", self.sp_t_max)
            f.addRow("Chunk Size:", self.sp_t_chunk)
            f.addRow("Retry Count:", self.sp_t_retry)
            f.addRow("Timeout (s):", self.sp_t_timeout)
            f.addRow("", self.chk_t_stream)
            f.addRow("", self.chk_t_mem)
            layout.addWidget(g)
            
            s = SettingsManager().settings
            self.cb_t_prov.setCurrentText(s.translation_provider)
            self.sp_t_temp.setValue(s.translation_temperature)
            self.sp_t_topp.setValue(s.translation_top_p)
            self.sp_t_chunk.setValue(s.translation_chunk_size)
            self.sp_t_retry.setValue(s.translation_retry)
        return self._create_scroll_panel(builder)
        
    def _build_ocr(self):
        def builder(layout):
            g = MaterialGroupBox("OCR Configuration")
            f = QFormLayout(g)
            self.cb_o_eng = MaterialComboBox(); self.cb_o_eng.addItems(["tesseract", "manga-ocr"])
            self.cb_o_lang = MaterialComboBox(); self.cb_o_lang.addItems(["eng", "jpn", "kor"])
            self.sp_o_dpi = MaterialSpinBox(); self.sp_o_dpi.setRange(72, 600)
            self.sp_o_conf = MaterialDoubleSpinBox(); self.sp_o_conf.setRange(0, 1)
            self.chk_o_rot = MaterialCheckBox("Auto Rotate")
            self.chk_o_deskew = MaterialCheckBox("Deskew")
            self.chk_o_denoise = MaterialCheckBox("Denoise")
            
            f.addRow("Engine:", self.cb_o_eng)
            f.addRow("Language:", self.cb_o_lang)
            f.addRow("DPI:", self.sp_o_dpi)
            f.addRow("Confidence Threshold:", self.sp_o_conf)
            f.addRow("", self.chk_o_rot)
            f.addRow("", self.chk_o_deskew)
            f.addRow("", self.chk_o_denoise)
            layout.addWidget(g)
            
            s = SettingsManager().settings
            self.cb_o_eng.setCurrentText(s.ocr_engine)
            self.cb_o_lang.setCurrentText(s.ocr_language)
            self.sp_o_dpi.setValue(s.ocr_dpi)
            self.sp_o_conf.setValue(s.ocr_confidence_threshold)
            self.chk_o_deskew.setChecked(s.ocr_preprocess_deskew)
            self.chk_o_denoise.setChecked(s.ocr_preprocess_denoise)
        return self._create_scroll_panel(builder)
        
    def _build_pdf(self):
        def builder(layout):
            g = MaterialGroupBox("PDF Viewer Configuration")
            f = QFormLayout(g)
            self.cb_p_zoom = MaterialComboBox(); self.cb_p_zoom.addItems(["100%", "Fit Width", "Fit Page"])
            self.chk_p_fit = MaterialCheckBox("Start with Fit Width")
            self.sp_p_thumb = MaterialSpinBox(); self.sp_p_thumb.setRange(50, 300); self.sp_p_thumb.setValue(150)
            self.sp_p_cache = MaterialSpinBox(); self.sp_p_cache.setRange(10, 1000); self.sp_p_cache.setValue(100)
            self.cb_p_qual = MaterialComboBox(); self.cb_p_qual.addItems(["High", "Medium", "Fast"])
            
            f.addRow("Default Zoom:", self.cb_p_zoom)
            f.addRow("Thumbnail Size (px):", self.sp_p_thumb)
            f.addRow("Cache Size (MB):", self.sp_p_cache)
            f.addRow("Render Quality:", self.cb_p_qual)
            f.addRow("", self.chk_p_fit)
            layout.addWidget(g)
        return self._create_scroll_panel(builder)
        
    def _build_export(self):
        def builder(layout):
            g = MaterialGroupBox("Export Configuration")
            f = QFormLayout(g)
            self.cb_e_fmt = MaterialComboBox(); self.cb_e_fmt.addItems(["PDF", "DOCX", "TXT", "HTML"])
            
            hbox = QHBoxLayout()
            self.le_e_folder = MaterialTextField()
            btn_browse = MaterialButton("Browse...")
            hbox.addWidget(self.le_e_folder)
            hbox.addWidget(btn_browse)
            
            self.chk_e_comp = MaterialCheckBox("Enable Compression")
            self.cb_e_over = MaterialComboBox(); self.cb_e_over.addItems(["Ask", "Overwrite", "Rename"])
            self.chk_e_meta = MaterialCheckBox("Preserve Original Metadata")
            
            f.addRow("Default Format:", self.cb_e_fmt)
            f.addRow("Output Folder:", hbox)
            f.addRow("Overwrite Policy:", self.cb_e_over)
            f.addRow("", self.chk_e_comp)
            f.addRow("", self.chk_e_meta)
            layout.addWidget(g)
            
            s = SettingsManager().settings
            self.chk_e_comp.setChecked(s.export_compression)
            self.chk_e_meta.setChecked(s.export_metadata)
            self.le_e_folder.setText(s.export_last_folder)
        return self._create_scroll_panel(builder)
        
    def _build_performance(self):
        def builder(layout):
            g = MaterialGroupBox("Performance & Resource Limits")
            f = QFormLayout(g)
            self.sp_perf_w = MaterialSpinBox(); self.sp_perf_w.setRange(1, 32); self.sp_perf_w.setValue(4)
            self.chk_perf_gpu = MaterialCheckBox("Enable GPU Acceleration")
            self.sp_perf_cpu = MaterialSpinBox(); self.sp_perf_cpu.setRange(10, 100); self.sp_perf_cpu.setValue(80)
            self.sp_perf_cache = MaterialSpinBox(); self.sp_perf_cache.setRange(128, 8192); self.sp_perf_cache.setValue(1024)
            self.sp_perf_mem = MaterialSpinBox(); self.sp_perf_mem.setRange(1024, 64000); self.sp_perf_mem.setValue(4096)
            
            f.addRow("Max Worker Threads:", self.sp_perf_w)
            f.addRow("CPU Usage Limit (%):", self.sp_perf_cpu)
            f.addRow("Global Cache (MB):", self.sp_perf_cache)
            f.addRow("Hard Memory Limit (MB):", self.sp_perf_mem)
            f.addRow("", self.chk_perf_gpu)
            layout.addWidget(g)
        return self._create_scroll_panel(builder)
        
    def _build_network(self):
        def builder(layout):
            g = MaterialGroupBox("Network Configuration")
            f = QFormLayout(g)
            self.le_n_proxy = MaterialTextField(); self.le_n_proxy.setPlaceholderText("http://127.0.0.1:8080")
            self.sp_n_timeout = MaterialSpinBox(); self.sp_n_timeout.setRange(5, 120); self.sp_n_timeout.setValue(30)
            self.sp_n_retry = MaterialSpinBox(); self.sp_n_retry.setRange(0, 10); self.sp_n_retry.setValue(3)
            self.chk_n_ssl = MaterialCheckBox("Verify SSL Certificates")
            self.chk_n_ssl.setChecked(True)
            
            f.addRow("Proxy URL:", self.le_n_proxy)
            f.addRow("Connection Timeout (s):", self.sp_n_timeout)
            f.addRow("Max Retries:", self.sp_n_retry)
            f.addRow("", self.chk_n_ssl)
            layout.addWidget(g)
        return self._create_scroll_panel(builder)
        
    def _build_storage(self):
        def builder(layout):
            g = MaterialGroupBox("Storage & Cache Management")
            f = QFormLayout(g)
            f.addRow("Total Cache Size:", MaterialLabel("1.42 GB"))
            f.addRow("Thumbnail Cache:", MaterialLabel("350 MB"))
            f.addRow("Translation Cache:", MaterialLabel("15 MB"))
            f.addRow("OCR Cache:", MaterialLabel("1.05 GB"))
            
            hbox = QHBoxLayout()
            btn_clear = MaterialButton("Clear All Cache")
            btn_rebuild = MaterialButton("Rebuild Index")
            btn_clear.setStyleSheet("background-color: var(--md-sys-color-error); color: var(--md-sys-color-on-error);")
            hbox.addWidget(btn_clear)
            hbox.addWidget(btn_rebuild)
            hbox.addStretch()
            
            f.addRow("", hbox)
            layout.addWidget(g)
        return self._create_scroll_panel(builder)
        
    def _build_updates(self):
        def builder(layout):
            g = MaterialGroupBox("Application Updates")
            f = QFormLayout(g)
            f.addRow("Current Version:", MaterialLabel("<b>v6.0.0</b> (Build 84920)"))
            
            self.cb_u_chan = MaterialComboBox(); self.cb_u_chan.addItems(["Stable", "Beta", "Nightly"])
            btn_check = MaterialButton("Check for Updates")
            
            f.addRow("Release Channel:", self.cb_u_chan)
            f.addRow("", btn_check)
            layout.addWidget(g)
        return self._create_scroll_panel(builder)
        
    def _build_advanced(self):
        def builder(layout):
            g = MaterialGroupBox("Advanced Developer Options")
            f = QFormLayout(g)
            self.chk_a_debug = MaterialCheckBox("Enable Developer/Debug Mode")
            self.cb_a_log = MaterialComboBox(); self.cb_a_log.addItems(["ERROR", "WARNING", "INFO", "DEBUG", "TRACE"])
            self.cb_a_log.setCurrentText("INFO")
            
            f.addRow("Logging Level:", self.cb_a_log)
            f.addRow("", self.chk_a_debug)
            
            hbox = QHBoxLayout()
            btn_conf = MaterialButton("Open Config Folder")
            btn_log = MaterialButton("Open Log Folder")
            btn_reset = MaterialButton("Factory Reset Settings")
            btn_reset.setStyleSheet("background-color: var(--md-sys-color-error); color: var(--md-sys-color-on-error);")
            
            hbox.addWidget(btn_conf)
            hbox.addWidget(btn_log)
            hbox.addStretch()
            f.addRow("", hbox)
            f.addRow("", btn_reset)
            
            layout.addWidget(g)
        return self._create_scroll_panel(builder)
        
    def _build_about(self):
        def builder(layout):
            g = MaterialGroupBox("About PDF Translater")
            lbl = MaterialLabel(
                "<h2>PDF Translater Workspace</h2>"
                "<p>Version 6.0.0<br/>"
                "A comprehensive AI-powered application for translating and extracting data from documents.</p>"
                "<p>&copy; 2026 Developer Team.</p>"
            )
            lbl.setWordWrap(True)
            layout.addWidget(g)
            g_layout = QVBoxLayout(g)
            g_layout.addWidget(lbl)
        return self._create_scroll_panel(builder)
        
    def hideEvent(self, event):
        # Save values dynamically on exit
        s = SettingsManager().settings
        s.translation_temperature = self.sp_t_temp.value()
        s.translation_top_p = self.sp_t_topp.value()
        s.translation_chunk_size = self.sp_t_chunk.value()
        s.translation_retry = self.sp_t_retry.value()
        s.translation_provider = self.cb_t_prov.currentText()
        
        s.ocr_engine = self.cb_o_eng.currentText()
        s.ocr_language = self.cb_o_lang.currentText()
        s.ocr_dpi = self.sp_o_dpi.value()
        s.ocr_confidence_threshold = self.sp_o_conf.value()
        s.ocr_preprocess_deskew = self.chk_o_deskew.isChecked()
        s.ocr_preprocess_denoise = self.chk_o_denoise.isChecked()
        
        s.export_compression = self.chk_e_comp.isChecked()
        s.export_metadata = self.chk_e_meta.isChecked()
        
        # We explicitly skip backend hooks. SettingsManager will serialize everything.
        SettingsManager().save()
        super().hideEvent(event)
