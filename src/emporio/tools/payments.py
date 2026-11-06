"""Payment and shipping rules computed in code (never by the LLM). Manual §3 and §5."""
from __future__ import annotations

from .common import Ctx, brl, norm

PIX_DISCOUNT = 0.05

# Manual §3.1 — minimum installment value per installment tier.
# (Assumption: §3.1 is more specific than the table's generic "R$100 minimum", so §3.1 wins.)
_TIERS = [(1, 3, 50.0), (4, 6, 80.0), (7, 12, 100.0)]


def _min_installment(n: int) -> float:
    return next(m for lo, hi, m in _TIERS if lo <= n <= hi)


def payment_options(ctx: Ctx, amount: float, has_active_promotion: bool = False) -> dict:
    """Payment options for a total. Set has_active_promotion=True if the price already includes a promotion."""
    if amount <= 0:
        return {"error": "amount must be positive"}
    table = []
    for n in range(1, 13):
        per = round(amount / n, 2)
        if n == 1 or per >= _min_installment(n):
            table.append({"times": n, "each": brl(per)})
    top = table[-1]
    options = {
        "max_installments_no_interest": top["times"],
        "summary": f"up to {top['times']}x of {top['each']} with no interest" if top["times"] > 1 else "single payment only",
        "full_table_only_if_customer_asks": table,
    }
    if has_active_promotion:
        options["pix"] = {"price": brl(amount), "note": "No extra PIX discount: the price is already promotional (Manual §6.2)."}
    else:
        options["pix"] = {"price": brl(round(amount * (1 - PIX_DISCOUNT), 2)), "discount": "5%"}
    options["debit"] = "single payment, all card brands"
    options["boleto"] = "single payment, clears in up to 3 business days"
    options["split_payment"] = ("allowed (e.g. PIX + card)" if amount > 2000
                                else "only available for purchases above R$ 2.000,00")
    return options


_METRO = {"campo grande"}
_SHIPPING_TABLE = [
    {"service": "PAC (Correios)", "delivery_time": "5 to 12 business days", "tracking": True, "insurance": True},
    {"service": "SEDEX (Correios)", "delivery_time": "2 to 5 business days", "tracking": True, "insurance": True},
    {"service": "Jadlog (.package)", "delivery_time": "3 to 8 business days", "tracking": True, "insurance": True},
]


def shipping_quote(ctx: Ctx, city: str, order_total: float, large_item: bool = False) -> dict:
    """Shipping for a destination city. large_item: drums, digital pianos, double bass."""
    if norm(city) in _METRO:
        # Assumption: only Campo Grande counts as "metropolitan region" (manual does not list municipalities).
        free = order_total > 500
        return {"area": "Campo Grande metropolitan region", "delivery": "own motoboy, 1 to 3 business days; "
                "the customer is phoned before delivery",
                "fee": "free" if free else brl(35.0),
                "rule": "Free shipping above R$ 500,00; otherwise flat R$ 35,00.",
                "large_item_note": "Large items may need an individual quote." if large_item else None}
    return {"area": f"Outside the metropolitan region ({city})",
            "options": _SHIPPING_TABLE,
            "fee": "Cannot be calculated here: depends on ZIP code, weight and size — calculated automatically at checkout.",
            "all_shipments": "Tracking code and insurance against loss/damage included; if the package arrives damaged, "
                             "refuse it and contact the store immediately.",
            "large_item_note": "Large items (acoustic drums, digital pianos, double basses) need an individual quote." if large_item else None}
