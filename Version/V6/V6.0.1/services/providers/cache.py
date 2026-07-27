import sqlite3
import hashlib
import json
import os
from typing import Optional

class TranslationCache:
    """SQLite-backed cache for translations to avoid redundant API calls."""
    
    def __init__(self, db_path: str = "translations.db"):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    hash TEXT PRIMARY KEY,
                    prompt TEXT,
                    response TEXT,
                    provider TEXT,
                    model TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
    def _generate_hash(self, prompt: str, provider: str, model: str) -> str:
        data = f"{prompt}|{provider}|{model}".encode('utf-8')
        return hashlib.sha256(data).hexdigest()
        
    def get(self, prompt: str, provider: str, model: str) -> Optional[str]:
        h = self._generate_hash(prompt, provider, model)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT response FROM cache WHERE hash=?", (h,))
            row = cursor.fetchone()
            if row:
                return row[0]
        return None
        
    def set(self, prompt: str, response: str, provider: str, model: str) -> None:
        h = self._generate_hash(prompt, provider, model)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO cache (hash, prompt, response, provider, model)
                VALUES (?, ?, ?, ?, ?)
            ''', (h, prompt, response, provider, model))
