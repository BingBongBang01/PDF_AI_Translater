import os
import json
import csv
from pathlib import Path
from typing import Dict, Any

try:
    import yaml
except ImportError:
    yaml = None

class GlossaryParser:
    """Parses JSON, YAML, and CSV glossaries with memory caching."""
    
    _cache: Dict[str, Dict[str, str]] = {}

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()

    @classmethod
    def load(cls, path: str, profile: str = "default") -> Dict[str, str]:
        if not path:
            return {}
            
        cache_key = f"{path}::{profile}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        p = Path(path)
        if not p.exists():
            from pdf_engine.logger import get_logger
            get_logger().log(f"[WARNING] Glossary file not found: {path}", level="WARN")
            return {}

        ext = p.suffix.lower()
        data = {}
        
        try:
            if ext == ".json":
                data = cls._parse_json(p)
            elif ext in (".yaml", ".yml"):
                data = cls._parse_yaml(p)
            elif ext == ".csv":
                data = cls._parse_csv(p)
            else: # fallback to legacy line-by-line
                data = cls._parse_txt(p)
                
            # If the data is structured by profiles (e.g. {"academic": {"Deep Research": "심층 연구"}})
            # we extract the specific profile. If the profile doesn't exist, or if the file is just flat,
            # we assume it's a flat dictionary.
            result = {}
            if profile in data and isinstance(data[profile], dict):
                result = data[profile]
            elif "default" in data and isinstance(data["default"], dict) and profile == "default":
                result = data["default"]
            else:
                # Flat structure, filter out nested dicts which might be other profiles
                for k, v in data.items():
                    if isinstance(v, str):
                        result[k] = v

            cls._cache[cache_key] = result
            return result
            
        except Exception as e:
            from pdf_engine.logger import get_logger
            get_logger().log(f"[ERROR] Failed to parse glossary {path}: {e}", level="ERROR")
            return {}

    @classmethod
    def _parse_json(cls, p: Path) -> Dict[str, Any]:
        return json.loads(p.read_text(encoding="utf-8"))

    @classmethod
    def _parse_yaml(cls, p: Path) -> Dict[str, Any]:
        if not yaml:
            raise RuntimeError("PyYAML is required to parse .yaml glossaries")
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    @classmethod
    def _parse_csv(cls, p: Path) -> Dict[str, Any]:
        result = {}
        with open(p, 'r', encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    result[row[0].strip()] = row[1].strip()
        return result

    @classmethod
    def _parse_txt(cls, p: Path) -> Dict[str, Any]:
        result = {}
        for raw in p.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            if "=>" in raw:
                src, dst = raw.split("=>", 1)
                result[src.strip()] = dst.strip()
            elif "," in raw:
                src, dst = raw.split(",", 1)
                result[src.strip()] = dst.strip()
        return result
