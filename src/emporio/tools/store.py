"""Static store facts (Manual §1.2, §2) and opening-hours logic."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from .common import Ctx

STORE = {
    "name": "Empório da Música",
    "tagline": "Sua música começa aqui.",
    "address": "Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, CEP 79202-333",
    "phone": "(67) 3341-4444",
    "whatsapp": "(67) 3321-4500",
    "email": "contato@emporiodamusica.com.br",
    "opening_hours": {"Mon-Fri": "09:00-18:00", "Sat": "09:00-13:00", "Sun & holidays": "closed"},
    "sells": "Musical instruments only (guitars, basses, acoustic guitars, drums, keyboards, winds, orchestral strings, ukuleles). "
             "No accessories: strings, picks, cables, cases, pedals, amplifiers.",
    "notes": "Phone vs WhatsApp numbers differ in the manual (3341-4444 vs 3321-4500); both are given. "
             "Special dates (Black Friday, store anniversary, Christmas) may have extended hours, announced on social media.",
}

# weekday(): Mon=0 … Sun=6
_HOURS = {**{d: (time(9), time(18)) for d in range(5)}, 5: (time(9), time(13))}


def store_info(ctx: Ctx) -> dict:
    return STORE


def _next_opening(dt: datetime) -> datetime:
    for add in range(0, 8):
        day = dt + timedelta(days=add)
        h = _HOURS.get(day.weekday())
        if not h:
            continue
        start = day.replace(hour=h[0].hour, minute=0, second=0, microsecond=0)
        if start > dt:
            return start
    raise RuntimeError("unreachable")


def is_open_now(ctx: Ctx) -> dict:
    dt = ctx.now
    h = _HOURS.get(dt.weekday())
    open_now = bool(h and h[0] <= dt.time() < h[1])
    out = {"now": dt.strftime("%A, %d/%m/%Y %H:%M"), "is_open": open_now,
           "caveat": "Public holidays are not in the manual's data; if today is a holiday the store is closed."}
    if not open_now:
        nxt = _next_opening(dt)
        out["next_opening"] = nxt.strftime("%A, %d/%m/%Y at %H:%M")
    else:
        out["closes_at"] = h[1].strftime("%H:%M")
    return out
