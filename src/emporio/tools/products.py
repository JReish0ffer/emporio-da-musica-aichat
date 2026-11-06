"""Product catalog tools: search, details, pricing with ACTIVE promotions only."""
from __future__ import annotations

import json

from rapidfuzz import fuzz

from .common import Ctx, brl, norm

PIX_DISCOUNT = 0.05  # Manual §3 — never stacks with promotional prices (§6.2)

_STATUS_LABEL = {
    "active": "available",
    "discontinued": "discontinued (no longer in catalog)",
    "coming_soon": "coming soon (not yet on sale)",
}


def _promo(ctx: Ctx, product_id: int):
    """Best ACTIVE promotion for a product. `is_active` is the source of truth, not the promo name."""
    return ctx.conn.execute(
        "SELECT discount_percent, description FROM promotions WHERE product_id=? AND is_active=1 "
        "ORDER BY discount_percent DESC LIMIT 1", (product_id,)).fetchone()


def _availability(row) -> str:
    # Status wins over stock: a discontinued/coming_soon item is never offered even if stock > 0.
    if row["status"] != "active":
        return row["status"]
    return "in_stock" if row["stock_quantity"] > 0 else "out_of_stock"


def present(ctx: Ctx, row, full: bool = False) -> dict:
    price = float(row["price_brl"])
    promo = _promo(ctx, row["product_id"]) if row["status"] == "active" else None
    avail = _availability(row)
    out = {
        "product_id": row["product_id"],
        "name": row["name"],
        "category": row["category"],
        "availability": avail,
        "units_in_stock": row["stock_quantity"] if avail == "in_stock" else 0,
        "list_price": brl(price),
    }
    if promo:
        final = round(price * (1 - promo["discount_percent"] / 100), 2)
        out["promotion"] = {
            "name": promo["description"], "discount_percent": promo["discount_percent"],
            "original_price": brl(price), "promo_price": brl(final),
            "note": "Promotional price: PIX 5% discount does NOT apply on top of it.",
        }
        out["effective_price_value"] = final
    else:
        out["pix_price"] = brl(round(price * (1 - PIX_DISCOUNT), 2))
        out["effective_price_value"] = price
    if avail != "in_stock":
        out["status_note"] = _STATUS_LABEL.get(row["status"], "") if row["status"] != "active" else "temporarily out of stock"
    if full:
        out["description"] = row["description"]
        out["specs"] = json.loads(row["specs"] or "{}")
    return out


_SELECT = """SELECT p.*, c.name AS category FROM products p JOIN categories c USING(category_id)"""


def _spec(row, key):
    return norm(str(json.loads(row["specs"] or "{}").get(key, "")))


def search_products(ctx: Ctx, query: str | None = None, category: str | None = None,
                    max_price: float | None = None, min_price: float | None = None,
                    string_type: str | None = None, electric: bool | None = None,
                    color: str | None = None, only_available: bool = True, limit: int = 8) -> dict:
    rows = ctx.conn.execute(_SELECT).fetchall()
    results = []
    cat_n = norm(category)
    for r in rows:
        if only_available and _availability(r) != "in_stock":
            continue
        if cat_n and not (cat_n in norm(r["category"]) or norm(r["category"]) in cat_n
                          or fuzz.partial_ratio(cat_n, norm(r["category"])) >= 88):
            continue
        if string_type and _spec(r, "strings") != norm(string_type):
            continue
        if electric is not None and _spec(r, "electronics") != ("yes" if electric else "no"):
            continue
        if color and norm(color) not in _spec(r, "color"):
            continue
        if query:
            hay = norm(f"{r['name']} {r['description']}")
            if not all(tok in hay for tok in norm(query).split()):
                continue
        p = present(ctx, r)
        price = p["effective_price_value"]
        if max_price is not None and price > max_price:
            continue
        if min_price is not None and price < min_price:
            continue
        results.append(p)
    results.sort(key=lambda p: p["effective_price_value"])
    total = len(results)
    for p in results:
        p.pop("effective_price_value")
    return {
        "total_matches": total,
        "shown": min(total, limit),
        "products": results[:limit],
        "filters_note": "Prices compared using the effective price (active promotion applied)."
        + (" Only items in stock are listed." if only_available else ""),
    }


def _find(ctx: Ctx, name: str, threshold: int = 72):
    rows = ctx.conn.execute(_SELECT).fetchall()
    q = norm(name)
    scored = sorted(((max(fuzz.token_set_ratio(q, norm(r["name"])), fuzz.partial_ratio(q, norm(r["name"]))), r)
                     for r in rows), key=lambda t: -t[0])
    return [(s, r) for s, r in scored if s >= threshold][:5]


def get_product(ctx: Ctx, name: str) -> dict:
    """Fuzzy lookup by name/model. Returns the product, or candidates when ambiguous."""
    matches = _find(ctx, name)
    if not matches:
        return {"found": False, "message": "No product in the catalog matches that name."}
    top = matches[0][0]
    tied = [r for s, r in matches if s >= top - 3]
    if len(tied) > 1:
        # Tie-break: a name that contains every query word as a whole token beats a near miss ("D-28" vs "D-28E").
        q_tokens = set(norm(name).split())
        exact = [r for r in tied if q_tokens <= set(norm(r["name"]).split())]
        if len(exact) == 1:
            tied = exact
    if len(tied) > 1:
        return {"found": False, "ambiguous": True,
                "message": "Several products match; ask the customer which one.",
                "candidates": [{"product_id": r["product_id"], "name": r["name"],
                                "list_price": brl(r["price_brl"])} for r in tied]}
    row = tied[0]
    out = {"found": True, "product": present(ctx, row, full=True)}
    out["product"].pop("effective_price_value", None)
    if _availability(row) != "in_stock":
        out["alternatives"] = _alternatives(ctx, row)
    return out


def _alternatives(ctx: Ctx, row, n: int = 3) -> list[dict]:
    """Similar items that ARE available: same category, closest price (Manual §7.3)."""
    price = float(row["price_brl"])
    cands = [r for r in ctx.conn.execute(_SELECT + " WHERE p.category_id=?", (row["category_id"],))
             if r["product_id"] != row["product_id"] and _availability(r) == "in_stock"]
    cands.sort(key=lambda r: abs(float(r["price_brl"]) - price))
    out = []
    for r in cands[:n]:
        p = present(ctx, r)
        p.pop("effective_price_value")
        out.append(p)
    return out


def list_categories(ctx: Ctx) -> dict:
    rows = ctx.conn.execute(
        """SELECT c.name, COUNT(CASE WHEN p.status='active' AND p.stock_quantity>0 THEN 1 END) AS n
           FROM categories c LEFT JOIN products p USING(category_id) GROUP BY c.category_id""").fetchall()
    return {"categories": [{"name": r["name"], "products_available": r["n"]} for r in rows],
            "note": "Categories with 0 available products cannot be offered right now."}


def active_promotions(ctx: Ctx) -> dict:
    rows = ctx.conn.execute(
        _SELECT + " JOIN promotions pr USING(product_id) WHERE pr.is_active=1").fetchall()
    out = []
    for r in rows:
        p = present(ctx, r)
        p.pop("effective_price_value", None)
        out.append(p)
    return {"active_promotions": out,
            "note": "Only promotions flagged active in the system exist right now; never promise others."}
