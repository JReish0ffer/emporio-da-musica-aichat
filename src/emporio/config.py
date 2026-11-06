"""Central configuration: paths, model, and the store's notion of "now"."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DB_PATH = Path(os.getenv("EMPORIO_DB", ROOT / "emporio.sqlite3"))
POLICY_PDF = DATA_DIR / "políticas_da_loja.pdf"
CSV_PREFIX = "desafio_tecnico_ai_eng - "

TZ = ZoneInfo("America/Campo_Grande")
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
MAX_TOOL_ROUNDS = 6


def now() -> datetime:
    """Current time in the store's timezone.

    ``STORE_NOW`` (ISO-8601) freezes the clock so demos/tests are reproducible
    (the sample orders end in March 2026, so "today" would otherwise make every
    delivered order fall outside the 7-day regret window).
    """
    frozen = os.getenv("STORE_NOW")
    if frozen:
        dt = datetime.fromisoformat(frozen)
        return dt if dt.tzinfo else dt.replace(tzinfo=TZ)
    return datetime.now(TZ)
