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
import sys
from pathlib import Path
from typing import Dict, Optional

# 기본 캐시 디렉터리 및 DB 파일 경로 설정
_DEFAULT_CACHE_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "PDFTranslaterGUI" / "cache"
_DEFAULT_CACHE_DB = _DEFAULT_CACHE_DIR / "translation_cache.db"

# 캐시 키에 섞는 스키마 버전. 과거 세그먼트-ID 오배정 버그(로컬 소형 모델이 응답
# 순서는 맞으면서도 segment_id만 엉뚱하게 베껴, 완전히 다른 위치의 세그먼트 원문에
# 잘못된 번역문이 캐시로 영구 저장된 문제 - 실제 확인됨: 재번역해도 같은 자리에 같은
# 오류가 재현됨, 원인이 새 번역이 아니라 오염된 캐시 재사용이었음)를 코드로 고쳐도,
# 이미 DB에 저장된 잘못된 (원문 -> 번역문) 쌍은 그대로 남아 계속 재사용된다. 버전을
# 올리면 기존 캐시 키가 전부 새 키와 달라져 오염된 과거 항목을 다시 읽지 않게 되고
# (DB에서 삭제하지 않으니 안전), 이후 정상 동작으로 생성된 항목만 새로 쌓인다.
_CACHE_SCHEMA_VERSION = "v3"


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
        raw_str = f"{_CACHE_SCHEMA_VERSION}||{source_text.strip()}||{source_lang.strip()}||{target_lang.strip()}||{g_hash}"
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

        keys_map = {}
        for src in sources:
            k = self.compute_key(src, source_lang, target_lang, glossary_text)
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
            key = self.compute_key(src, source_lang, target_lang, glossary_text)
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

    def get_stats(self) -> dict:
        """
        캐시 DB의 총 레코드 수, 파일 크기(MB), DB 경로를 반환한다.
        """
        count = 0
        size_mb = 0.0
        try:
            if self.db_path.exists():
                size_mb = round(self.db_path.stat().st_size / (1024 * 1024), 2)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM translations")
                count = cursor.fetchone()[0]
        except Exception:
            pass
        return {
            "count": count,
            "size_mb": size_mb,
            "db_path": str(self.db_path)
        }

    def clear(self) -> bool:
        """
        캐시 DB의 모든 번역 레코드를 삭제한다.
        """
        try:
            conn = self._get_connection()
            conn.execute("DELETE FROM translations;")
            conn.commit()
            try:
                conn.isolation_level = None
                conn.execute("VACUUM;")
            except Exception:
                pass
            conn.close()
            return True
        except Exception as e:
            print(f"[캐시 비우기 오류] {e}", file=sys.stderr)
            return False


# 모듈 단위 글로벌 캐시 싱글톤 인스턴스
GLOBAL_CACHE = TranslationCache()

