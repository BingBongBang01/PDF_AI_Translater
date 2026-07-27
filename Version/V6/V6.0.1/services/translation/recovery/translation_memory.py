import json
from pathlib import Path
from typing import Optional
from core.logger import logger

class TranslationMemory:
    """Caches translations to avoid redundant API calls."""
    def __init__(self, cache_file: str = "config/tm.json"):
        self.cache_file = Path(cache_file)
        self.memory = {}
        self._load()
        
    def _load(self):
        if self.cache_file.exists():
            try:
                self.memory = json.loads(self.cache_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Could not load TM: {e}")
                
    def _save(self):
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(self.memory, ensure_ascii=False, indent=2), encoding="utf-8")
        
    def get_translation(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        key = f"{source_lang}_{target_lang}_{text}"
        return self.memory.get(key)
        
    def save_translation(self, text: str, translation: str, source_lang: str, target_lang: str):
        key = f"{source_lang}_{target_lang}_{text}"
        self.memory[key] = translation
        self._save()
