"""Conversation persistence in SQLite: sessions, messages (incl. tool traces) and verified customers."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime


class Memory:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def open_session(self, session_id: str, now: datetime) -> set[int]:
        row = self.conn.execute("SELECT verified_customers FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row:
            return set(json.loads(row["verified_customers"]))
        self.conn.execute("INSERT INTO sessions (session_id, created_at) VALUES (?,?)",
                          (session_id, now.isoformat(timespec="seconds")))
        self.conn.commit()
        return set()

    def save_verified(self, session_id: str, verified: set[int]) -> None:
        self.conn.execute("UPDATE sessions SET verified_customers=? WHERE session_id=?",
                          (json.dumps(sorted(verified)), session_id))
        self.conn.commit()

    def add(self, session_id: str, role: str, content: str, now: datetime, meta: dict | None = None) -> None:
        self.conn.execute("INSERT INTO messages (session_id, role, content, meta, created_at) VALUES (?,?,?,?,?)",
                          (session_id, role, content, json.dumps(meta, ensure_ascii=False) if meta else None,
                           now.isoformat(timespec="seconds")))
        self.conn.commit()

    def history(self, session_id: str, limit: int = 30) -> list[dict]:
        """Last `limit` user/assistant turns (tool traces are stored but not replayed, to keep context small)."""
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? AND role IN ('user','assistant') "
            "ORDER BY id DESC LIMIT ?", (session_id, limit)).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def drop_last(self, session_id: str, role: str) -> None:
        self.conn.execute("DELETE FROM messages WHERE id=(SELECT MAX(id) FROM messages WHERE session_id=? AND role=?)",
                          (session_id, role))
        self.conn.commit()
