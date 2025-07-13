"""
SQLite-backed chat persistence with corruption guards.
"""

from __future__ import annotations

import os
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
import shutil
import time

logger = logging.getLogger(__name__)

class ChatStorage:
    def __init__(self) -> None:
        root = Path.home() / "Library" / "Application Support" / "HandycapAI"
        root.mkdir(parents=True, exist_ok=True)
        self.db_path: Path = root / "chats.db"
        self._init_db()

    # ───────────────────────────────────────────────
    # Low-level helpers
    def _connection(self) -> sqlite3.Connection:
        try:
            return sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        except sqlite3.DatabaseError as exc:
            logger.error("SQLite error opening DB: %s", exc)
            self._handle_corruption()
            return sqlite3.connect(self.db_path, timeout=5, isolation_level=None)

    def _handle_corruption(self):
        """Rename corrupt DB and build a clean one so the app can continue."""
        ts = int(time.time())
        corrupt_path = self.db_path.with_suffix(f".corrupt-{ts}.db")
        try:
            shutil.move(self.db_path, corrupt_path)
            logger.warning("Database file was corrupt – moved to %s", corrupt_path)
        except Exception as exc:
            logger.error("Failed to move corrupt DB: %s", exc)
        self._init_db()

    def _safe_exec(self, sql: str, params=(), fetch: str | None = None):
        """
        Execute a SQL statement safely.
        fetch = 'one' | 'all' | None   -> how to retrieve results
        """
        try:
            with self._connection() as con:
                cur = con.execute(sql, params)
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return cur.fetchall()
        except sqlite3.DatabaseError as exc:
            logger.error("SQLite operation failed: %s", exc)
            self._handle_corruption()
            raise RuntimeError("The local chat history database was damaged and had to be reset.")

    # ───────────────────────────────────────────────
    # Schema
    def _init_db(self):
        try:
            with self._connection() as con:
                con.executescript(
                    """
                    PRAGMA journal_mode=WAL;

                    CREATE TABLE IF NOT EXISTS chats (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        title       TEXT,
                        created_at  TIMESTAMP,
                        updated_at  TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS messages (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id     INTEGER,
                        role        TEXT NOT NULL,
                        content     TEXT NOT NULL,
                        screenshot  BLOB,
                        created_at  TIMESTAMP,
                        FOREIGN KEY (chat_id) REFERENCES chats(id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_messages_chat_id
                        ON messages(chat_id);

                    CREATE INDEX IF NOT EXISTS idx_messages_created_at
                        ON messages(created_at);
                    """
                )
        except Exception as exc:
            logger.error("DB initialisation failed: %s", exc)
            self._handle_corruption()

    # ───────────────────────────────────────────────
    # Public API
    def create_chat(self, title: str = "") -> int:
        self._safe_exec(
            "INSERT INTO chats(title,created_at,updated_at) VALUES (?,?,?)",
            (title, datetime.now(), datetime.now()),
        )
        row = self._safe_exec("SELECT last_insert_rowid()", fetch="one")
        return int(row[0])  # type: ignore[index]

    def add_message(
        self, chat_id: int, role: str, content: str, screenshot: bytes | None = None
    ):
        self._safe_exec(
            "INSERT INTO messages(chat_id,role,content,screenshot,created_at) VALUES (?,?,?,?,?)",
            (chat_id, role, content, screenshot, datetime.now()),
        )
        self._safe_exec(
            "UPDATE chats SET updated_at=? WHERE id=?", (datetime.now(), chat_id)
        )

    def get_messages(self, chat_id: int, limit: Optional[int] = None) -> List[Dict]:
        sql = "SELECT role,content,created_at FROM messages WHERE chat_id=? ORDER BY created_at DESC"
        if limit:
            sql += f" LIMIT {limit}"
        rows = self._safe_exec(sql, (chat_id,), fetch="all") or []
        rows.reverse()  # chronological order
        return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]

    def get_all_chats(self) -> List[Dict]:
        rows = self._safe_exec(
            "SELECT id,title,updated_at FROM chats ORDER BY updated_at DESC", fetch="all"
        ) or []
        return [{"id": r[0], "title": r[1] or f"Chat {r[0]}", "updated_at": r[2]} for r in rows]

    def update_chat_title(self, chat_id: int, title: str):
        self._safe_exec(
            "UPDATE chats SET title=?,updated_at=? WHERE id=?",
            (title, datetime.now(), chat_id),
        )