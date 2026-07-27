# -*- coding: utf-8 -*-
"""
pdf_engine/cache.py — SQLite 기반 번역 결과 영구 캐시 모듈.

동일한 원문, 원문 언어, 번역 대상 언어, 용어집 조합에 대한 번역 결과를
로컬 SQLite DB에 저장하여, 재번역 시 API 호출 없이 0.01초 내로 빠르게 복원한다.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Dict, Optional

# 기본 캐시 디렉터리 및 DB 파일 경로 설정
_DEFAULT_CACHE_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "PDFTranslaterGUI" / "cache"
_DEFAULT_CACHE_DB = _DEFAULT_CACHE_DIR / "translation_cache.db"


class TranslationCache:
    """
    SQLite 기반의 번역 디스크 캐시 관리 클래스.
    Thread-safe 연결 방식을 지원한다.
    """

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path or _DEFAULT_CACHE_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    cache_key TEXT PRIMARY KEY,
                    source_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    glossary_hash TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_key ON translations(cache_key);"
            )

    @staticmethod
    def compute_key(source_text: str, source_lang: str, target_lang: str, glossary_text: str = "") -> str:
        """
        원문 텍스트, 언어 설정, 용어집 내용의 해시값을 기반으로 캐시 키를 생성한다.
        """
        g_hash = hashlib.md5(glossary_text.encode("utf-8")).hexdigest() if glossary_text else ""
        raw_str = f"{source_text.strip()}||{source_lang.strip()}||{target_lang.strip()}||{g_hash}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def get(self, source_text: str, source_lang: str, target_lang: str, glossary_text: str = "") -> Optional[str]:
        """
        캐시된 번역문이 존재하면 반환하고, 없으면 None을 반환한다.
        """
        key = self.compute_key(source_text, source_lang, target_lang, glossary_text)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT translated_text FROM translations WHERE cache_key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception:
            pass
        return None

    def get_batch(self, sources: list[str], source_lang: str, target_lang: str, glossary_text: str = "") -> Dict[str, str]:
        """
        여러 세그먼트의 원문에 대해 캐시된 번역 결과를 딕셔너리로 반환한다.
        """
        result = {}
        if not sources:
            return result

        g_hash = hashlib.md5(glossary_text.encode("utf-8")).hexdigest() if glossary_text else ""
        keys_map = {}
        for src in sources:
            k = hashlib.sha256(f"{src.strip()}||{source_lang.strip()}||{target_lang.strip()}||{g_hash}".encode("utf-8")).hexdigest()
            keys_map[k] = src

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join("?" for _ in keys_map)
                cursor.execute(
                    f"SELECT cache_key, translated_text FROM translations WHERE cache_key IN ({placeholders})",
                    list(keys_map.keys())
                )
                for k, trans in cursor.fetchall():
                    original_src = keys_map[k]
                    result[original_src] = trans
        except Exception:
            pass

        return result

    def set(self, source_text: str, translated_text: str, source_lang: str, target_lang: str, glossary_text: str = "") -> None:
        """
        단일 번역 결과를 캐시에 저장한다.
        """
        if not source_text or not translated_text:
            return
        key = self.compute_key(source_text, source_lang, target_lang, glossary_text)
        g_hash = hashlib.md5(glossary_text.encode("utf-8")).hexdigest() if glossary_text else ""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO translations
                    (cache_key, source_text, translated_text, source_lang, target_lang, glossary_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (key, source_text, translated_text, source_lang, target_lang, g_hash)
                )
        except Exception:
            pass

    def set_batch(self, mapping: Dict[str, str], source_lang: str, target_lang: str, glossary_text: str = "") -> None:
        """
        여러 번역 쌍 (원문 -> 번역문)을 캐시에 일괄 저장한다.
        """
        if not mapping:
            return
        g_hash = hashlib.md5(glossary_text.encode("utf-8")).hexdigest() if glossary_text else ""
        rows = []
        for src, dst in mapping.items():
            if not src or not dst:
                continue
            key = hashlib.sha256(f"{src.strip()}||{source_lang.strip()}||{target_lang.strip()}||{g_hash}".encode("utf-8")).hexdigest()
            rows.append((key, src, dst, source_lang, target_lang, g_hash))

        if not rows:
            return

        try:
            with self._get_connection() as conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO translations
                    (cache_key, source_text, translated_text, source_lang, target_lang, glossary_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    rows
                )
        except Exception:
            pass


# 모듈 단위 글로벌 캐시 싱글톤 인스턴스
GLOBAL_CACHE = TranslationCache()
