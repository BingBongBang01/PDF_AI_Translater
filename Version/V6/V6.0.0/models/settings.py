import json
import os
import base64
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

CONFIG_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "PDFTranslaterGUI"
CONFIG_PATH = CONFIG_DIR / "config.json"

@dataclass
class ApiKey:
    provider: str = "gemini"
    is_active: bool = False
    key: str = ""

@dataclass
class AppSettings:
    api_keys: List[ApiKey] = field(default_factory=list)
    source_lang: str = "English"
    target_lang: str = "한국어"
    model_npu: str = "gemma4-it-e2b-FLM"
    model_gpu: str = "Gemma-3-4b-it-GGUF"
    use_npu: bool = True
    runtime: str = "lemonade"
    use_gpu: bool = False
    compress: bool = True
    auto_open: bool = True
    chars: str = "1500"
    segs: str = "10"
    tokens: str = "8192"
    theme: str = "system"  # light, dark, system
    window_geometry: str = ""
    window_state: str = ""
    recent_files: List[str] = field(default_factory=list)
    last_zoom: float = 1.0
    last_pdf_page: int = 0
    viewer_mode: str = "continuous"
    pdf_panel_sizes: List[int] = field(default_factory=lambda: [200, 600, 200])
    translation_panel_sizes: List[int] = field(default_factory=lambda: [300, 300, 300])
    translation_provider: str = "Google Gemini"
    translation_temperature: float = 0.3
    translation_top_p: float = 1.0
    translation_context_len: int = 4000
    translation_chunk_size: int = 1500
    translation_parallel: int = 4
    translation_retry: int = 3
    translation_prompt: str = ""
    ocr_panel_sizes: List[int] = field(default_factory=lambda: [300, 400, 300])
    ocr_engine: str = "tesseract"
    ocr_language: str = "eng"
    ocr_multi_language: bool = False
    ocr_dpi: int = 300
    ocr_preprocess_deskew: bool = True
    ocr_preprocess_denoise: bool = True
    ocr_preprocess_contrast: bool = True
    ocr_preprocess_threshold: bool = True
    ocr_confidence_threshold: float = 0.8
    ocr_parallel: int = 4
    export_last_folder: str = ""
    export_recent_formats: List[str] = field(default_factory=lambda: ["PDF"])
    export_filename_template: str = "{name}_translated.{ext}"
    export_compression: bool = True
    export_metadata: bool = True

class SettingsManager:
    """Manages application configuration and persistence independent of the UI."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance.settings = AppSettings()
            cls._instance.load()
        return cls._instance

    def save(self):
        try:
            data = {
                "api_rows": [
                    {
                        "provider": k.provider,
                        "on": k.is_active,
                        "key": base64.b64encode(k.key.encode("utf-8")).decode("ascii")
                    } for k in self.settings.api_keys
                ],
                "src": self.settings.source_lang,
                "dst": self.settings.target_lang,
                "model_npu": self.settings.model_npu,
                "model_gpu": self.settings.model_gpu,
                "use_npu": self.settings.use_npu,
                "runtime": self.settings.runtime,
                "use_gpu": self.settings.use_gpu,
                "compress": self.settings.compress,
                "auto_open": self.settings.auto_open,
                "chars": self.settings.chars,
                "segs": self.settings.segs,
                "tokens": self.settings.tokens,
                "theme": self.settings.theme,
                "window_geometry": self.settings.window_geometry,
                "window_state": self.settings.window_state,
                "recent_files": self.settings.recent_files,
                "last_zoom": self.settings.last_zoom,
                "last_pdf_page": self.settings.last_pdf_page,
                "viewer_mode": self.settings.viewer_mode,
                "pdf_panel_sizes": self.settings.pdf_panel_sizes,
                "translation_panel_sizes": self.settings.translation_panel_sizes,
                "translation_provider": self.settings.translation_provider,
                "translation_temperature": self.settings.translation_temperature,
                "translation_top_p": self.settings.translation_top_p,
                "translation_context_len": self.settings.translation_context_len,
                "translation_chunk_size": self.settings.translation_chunk_size,
                "translation_parallel": self.settings.translation_parallel,
                "translation_retry": self.settings.translation_retry,
                "translation_prompt": self.settings.translation_prompt,
                "ocr_panel_sizes": self.settings.ocr_panel_sizes,
                "ocr_engine": self.settings.ocr_engine,
                "ocr_language": self.settings.ocr_language,
                "ocr_multi_language": self.settings.ocr_multi_language,
                "ocr_dpi": self.settings.ocr_dpi,
                "ocr_preprocess_deskew": self.settings.ocr_preprocess_deskew,
                "ocr_preprocess_denoise": self.settings.ocr_preprocess_denoise,
                "ocr_preprocess_contrast": self.settings.ocr_preprocess_contrast,
                "ocr_preprocess_threshold": self.settings.ocr_preprocess_threshold,
                "ocr_confidence_threshold": self.settings.ocr_confidence_threshold,
                "ocr_parallel": self.settings.ocr_parallel,
                "export_last_folder": self.settings.export_last_folder,
                "export_recent_formats": self.settings.export_recent_formats,
                "export_filename_template": self.settings.export_filename_template,
                "export_compression": self.settings.export_compression,
                "export_metadata": self.settings.export_metadata,
            }
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SettingsManager] Failed to save config: {e}")

    def load(self) -> bool:
        if not CONFIG_PATH.exists():
            return False
        
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            self.settings.api_keys.clear()
            rows = data.get("api_rows", [])
            for r in rows:
                key = ""
                try:
                    key = base64.b64decode(r.get("key", "").encode("ascii")).decode("utf-8")
                except Exception:
                    pass
                self.settings.api_keys.append(ApiKey(
                    provider=r.get("provider", "gemini"),
                    is_active=bool(r.get("on", False)),
                    key=key
                ))
            
            self.settings.source_lang = data.get("src", self.settings.source_lang)
            self.settings.target_lang = data.get("dst", self.settings.target_lang)
            self.settings.model_npu = data.get("model_npu", self.settings.model_npu)
            self.settings.model_gpu = data.get("model_gpu", self.settings.model_gpu)
            self.settings.use_npu = data.get("use_npu", self.settings.use_npu)
            self.settings.runtime = data.get("runtime", self.settings.runtime)
            self.settings.use_gpu = data.get("use_gpu", self.settings.use_gpu)
            self.settings.compress = data.get("compress", self.settings.compress)
            self.settings.auto_open = data.get("auto_open", self.settings.auto_open)
            self.settings.chars = data.get("chars", self.settings.chars)
            self.settings.segs = data.get("segs", self.settings.segs)
            self.settings.tokens = data.get("tokens", self.settings.tokens)
            self.settings.theme = data.get("theme", self.settings.theme)
            self.settings.window_geometry = data.get("window_geometry", self.settings.window_geometry)
            self.settings.window_state = data.get("window_state", self.settings.window_state)
            self.settings.recent_files = data.get("recent_files", self.settings.recent_files)
            self.settings.last_zoom = data.get("last_zoom", self.settings.last_zoom)
            self.settings.last_pdf_page = data.get("last_pdf_page", self.settings.last_pdf_page)
            self.settings.viewer_mode = data.get("viewer_mode", self.settings.viewer_mode)
            self.settings.pdf_panel_sizes = data.get("pdf_panel_sizes", self.settings.pdf_panel_sizes)
            self.settings.translation_panel_sizes = data.get("translation_panel_sizes", self.settings.translation_panel_sizes)
            self.settings.translation_provider = data.get("translation_provider", self.settings.translation_provider)
            self.settings.translation_temperature = data.get("translation_temperature", self.settings.translation_temperature)
            self.settings.translation_top_p = data.get("translation_top_p", self.settings.translation_top_p)
            self.settings.translation_context_len = data.get("translation_context_len", self.settings.translation_context_len)
            self.settings.translation_chunk_size = data.get("translation_chunk_size", self.settings.translation_chunk_size)
            self.settings.translation_parallel = data.get("translation_parallel", self.settings.translation_parallel)
            self.settings.translation_retry = data.get("translation_retry", self.settings.translation_retry)
            self.settings.translation_prompt = data.get("translation_prompt", self.settings.translation_prompt)
            self.settings.ocr_panel_sizes = data.get("ocr_panel_sizes", self.settings.ocr_panel_sizes)
            self.settings.ocr_engine = data.get("ocr_engine", self.settings.ocr_engine)
            self.settings.ocr_language = data.get("ocr_language", self.settings.ocr_language)
            self.settings.ocr_multi_language = data.get("ocr_multi_language", self.settings.ocr_multi_language)
            self.settings.ocr_dpi = data.get("ocr_dpi", self.settings.ocr_dpi)
            self.settings.ocr_preprocess_deskew = data.get("ocr_preprocess_deskew", self.settings.ocr_preprocess_deskew)
            self.settings.ocr_preprocess_denoise = data.get("ocr_preprocess_denoise", self.settings.ocr_preprocess_denoise)
            self.settings.ocr_preprocess_contrast = data.get("ocr_preprocess_contrast", self.settings.ocr_preprocess_contrast)
            self.settings.ocr_preprocess_threshold = data.get("ocr_preprocess_threshold", self.settings.ocr_preprocess_threshold)
            self.settings.ocr_confidence_threshold = data.get("ocr_confidence_threshold", self.settings.ocr_confidence_threshold)
            self.settings.ocr_parallel = data.get("ocr_parallel", self.settings.ocr_parallel)
            self.settings.export_last_folder = data.get("export_last_folder", self.settings.export_last_folder)
            self.settings.export_recent_formats = data.get("export_recent_formats", self.settings.export_recent_formats)
            self.settings.export_filename_template = data.get("export_filename_template", self.settings.export_filename_template)
            self.settings.export_compression = data.get("export_compression", self.settings.export_compression)
            self.settings.export_metadata = data.get("export_metadata", self.settings.export_metadata)
            return True
        except Exception as e:
            print(f"[SettingsManager] Failed to load config: {e}")
            return False
