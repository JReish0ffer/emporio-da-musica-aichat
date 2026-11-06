"""Shared helpers for tools."""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime


def norm(text: str | None) -> str:
    """Lowercase, strip accents/punctuation: 'Violão' -> 'violao'."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def brl(value: float) -> str:
    """Format as Brazilian currency: 2199 -> 'R$ 2.199,00'."""
    s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


@dataclass
class Ctx:
    """Per-conversation context handed to every tool."""
    conn: sqlite3.Connection
    now: datetime
    session_id: str = "default"
    verified_customers: set[int] = field(default_factory=set)
