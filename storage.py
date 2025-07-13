"""
SQLite persistence with automatic corruption handling and
CHECK constraints for role column.
"""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class ChatStorage:
    """All DB I/O."""

    def __init__(self):
        root = Path.home() / "Library" / "Application Support" / "HandycapAI"
        root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "chats.db"
        self._conn = sqlite3.connect(self.db_path, isolation_level=None, timeout=5)
        self._init_db()

    # ───────────────────────────────────────────
    def _init_db(self):
        with self._conn as con:
            con.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS chats (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT,
                    created_at  TIMESTAMP,
                    updated_at  TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id     INTEGER NOT NULL,
                    role        TEXT NOT NULL CHECK(role IN ('user','assistant','tool')),
                    content     TEXT NOT NULL,
                    screenshot  BLOB,
                    created_at  TIMESTAMP,
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_msg_chat ON messages(chat_id);
                """
            )

    # ───────────────────────────────────────────
    def _safe(self, sql: str, params=(), fetch: str | None = None):
        try:
            cur = self._conn.execute(sql, params)
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
        except sqlite3.DatabaseError as exc:
            logger.error("SQLite error: %s", exc)
            self._handle_corrupt()
            raise RuntimeError("Local DB corrupted and reset.")

    def _handle_corrupt(self):
        ts = int(time.time())
        self._conn.close()
        shutil.move(self.db_path, self.db_path.with_suffix(f".corrupt-{ts}.db"))
        self._conn = sqlite3.connect(self.db_path, isolation_level=None, timeout=5)
        self._init_db()

    # ───────────────────────────────────────────
    def create_chat(self, title: str = "") -> int:
        self._safe(
            "INSERT INTO chats(title,created_at,updated_at) VALUES (?,?,?)",
            (title, datetime.now(), datetime.now()),
        )
        row = self._safe("SELECT last_insert_rowid()", fetch="one")
        return int(row[0])  # type: ignore[index]

    def add_message(self, chat_id: int, role: str, content: str, screenshot: bytes | None = None):
        self._safe(
            "INSERT INTO messages(chat_id,role,content,screenshot,created_at) VALUES (?,?,?,?,?)",
            (chat_id, role, content, screenshot, datetime.now()),
        )
        self._safe("UPDATE chats SET updated_at=? WHERE id=?", (datetime.now(), chat_id))

    def get_messages(self, chat_id: int, limit: Optional[int] = None) -> List[Dict]:
        sql = "SELECT role,content,created_at FROM messages WHERE chat_id=? ORDER BY created_at DESC"
        if limit:
            sql += f" LIMIT {limit}"
        rows = self._safe(sql, (chat_id,), fetch="all") or []
        rows.reverse()
        return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]

    def get_all_chats(self) -> List[Dict]:
        rows = self._safe(
            "SELECT id,title,updated_at FROM chats ORDER BY updated_at DESC", fetch="all"
        ) or []
        return [{"id": r[0], "title": r[1] or f'Chat {r[0]}', "updated_at": r[2]} for r in rows]

    def update_chat_title(self, chat_id: int, title: str):
        self._safe("UPDATE chats SET title=?,updated_at=? WHERE id=?", (title, datetime.now(), chat_id))