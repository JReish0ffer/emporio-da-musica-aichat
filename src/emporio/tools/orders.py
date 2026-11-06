"""Order lookup (with customer verification), returns eligibility, and human hand-off.

Privacy (Manual §9, LGPD): order data is only released after the person proves who they are by giving the
e-mail or phone registered on that order. Failure messages are identical whether the order exists or not.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from .common import Ctx, brl

_STATUS = {
    "delivered": "delivered", "shipped": "shipped (on its way)", "confirmed": "payment confirmed, being prepared",
    "pending": "awaiting payment confirmation", "cancelled": "cancelled",
}
_FAIL = {"verified": False, "message": "Could not verify. To access an order I need the order number plus the "
         "e-mail or phone number registered on it. Do not reveal whether the order exists."}


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def verify_customer(ctx: Ctx, order_id: int, email_or_phone: str) -> dict:
    """Verify that `email_or_phone` belongs to the customer who owns `order_id`."""
    row = ctx.conn.execute(
        "SELECT c.customer_id, c.name, c.email, c.phone FROM orders o JOIN customers c USING(customer_id) "
        "WHERE o.order_id=?", (order_id,)).fetchone()
    given = (email_or_phone or "").strip().lower()
    ok = bool(row and given and (
        given == row["email"].lower()
        or (len(_digits(given)) >= 8 and _digits(given)[-9:] == _digits(row["phone"])[-9:])))
    if not ok:
        return _FAIL
    ctx.verified_customers.add(row["customer_id"])
    return {"verified": True, "customer_first_name": row["name"].split()[0]}


def _items(ctx: Ctx, order_id: int) -> list[dict]:
    rows = ctx.conn.execute(
        "SELECT p.name, i.quantity, p.price_brl FROM order_items i JOIN products p USING(product_id) "
        "WHERE i.order_id=?", (order_id,)).fetchall()
    return [{"product": r["name"], "quantity": r["quantity"]} for r in rows]


def _owned(ctx: Ctx, order_id: int):
    row = ctx.conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if row and row["customer_id"] in ctx.verified_customers:
        return row
    return None


def get_order(ctx: Ctx, order_id: int, email_or_phone: str | None = None) -> dict:
    """Order status, items, tracking. Verifies the customer first when not already verified this session."""
    if email_or_phone:
        v = verify_customer(ctx, order_id, email_or_phone)
        if not v["verified"]:
            return v
    o = _owned(ctx, order_id)
    if not o:
        return _FAIL
    out = {
        "order_id": o["order_id"], "order_date": o["order_date"], "status": _STATUS.get(o["status"], o["status"]),
        "items": _items(ctx, order_id), "total_paid": brl(o["total_brl"]),
        "payment_method": o["payment_method"], "estimated_delivery": o["estimated_delivery"],
    }
    if o["tracking_code"]:
        out["tracking_code"] = o["tracking_code"]
        out["tracking_note"] = "Check it on the Correios or Jadlog website."
    elif o["status"] in ("confirmed", "pending"):
        out["tracking_note"] = "No tracking code yet: it is sent by e-mail and WhatsApp as soon as the order is dispatched."
    if o["status"] == "cancelled":
        out["cancellation_reason"] = o["notes"]
    return out


# ---------------------------------------------------------------- returns (Manual §4, §8)
def evaluate_return(ctx: Ctx, order_id: int, reason: str) -> dict:
    """reason: 'regret' (changed mind), 'defect', or 'preference' (swap for another model/color)."""
    o = _owned(ctx, order_id)
    if not o:
        return {**_FAIL, "message": "Order must be verified first (ask for order number + registered e-mail/phone)."}
    if reason not in ("regret", "defect", "preference"):
        return {"error": "reason must be regret, defect or preference"}
    if o["status"] != "delivered":
        return {"eligible": None, "order_status": _STATUS.get(o["status"], o["status"]),
                "message": "A return/exchange only applies after delivery. For a not-yet-delivered or cancelled order, "
                           "offer to hand it to a human attendant (cancellations / refunds are done by the team)."}

    # ASSUMPTIONS (documented in README): the data has no real delivery date -> estimated_delivery stands in for
    # the receipt date; every order is treated as an online purchase (no sales-channel column).
    received = date.fromisoformat(o["estimated_delivery"])
    days = (ctx.now.date() - received).days
    base = {"order_id": order_id, "received_on_assumed": received.isoformat(), "days_since_receipt": days,
            "assumptions": "Receipt date approximated by the estimated delivery date; order treated as an online purchase."}

    items = [i["product"] for i in _items(ctx, order_id)]
    mouthpiece = [p for p in items if "boquilha" in p.lower()]
    caveat = ("Not eligible regardless of dates: customized/special-setup instruments, items sold as 'venda final' "
              "in clearance, and wind mouthpieces (hygiene). Confirm with the customer that none apply.")
    if mouthpiece:
        return {**base, "eligible": False, "rule": "§4.4", "message": "Mouthpieces cannot be returned (hygiene)."}

    if reason in ("regret", "preference"):
        ok = 0 <= days <= 7
        label = "§4.1 right of regret" if reason == "regret" else "§4.3 exchange for preference"
        res = {**base, "eligible": ok, "rule": label, "deadline_days": 7, "ineligible_items_check": caveat}
        if ok and reason == "regret":
            res["how_it_works"] = ("Item must be in original packaging, unused, with all accessories and manuals. "
                                   "Refund to the original payment method within 10 business days. "
                                   "Return shipping is paid by the store.")
        elif ok:
            res["how_it_works"] = ("Subject to availability of the desired product; item in perfect condition and "
                                   "original packaging; price difference charged or refunded.")
        else:
            res["window_expired_on"] = (received + timedelta(days=7)).isoformat()
            res["next_step"] = ("The 7-day window has passed. If the instrument has a manufacturing defect, a defect "
                                "exchange or warranty may still apply. Otherwise offer a human attendant.")
        return res

    # defect
    if days <= 30:
        return {**base, "eligible": True, "rule": "§4.2 defect exchange (30 days)", "ineligible_items_check": caveat,
                "exclusions": "Damage from misuse, drops, excess humidity or unauthorized modifications is not covered.",
                "next_step": "Offer to open a human ticket so the team arranges inspection/exchange."}
    legal_ok = days <= 90
    return {**base, "eligible": False, "rule": "§4.2 (30 days) expired",
            "legal_warranty": f"Legal warranty of 90 days from receipt (§8.1) {'still applies' if legal_ok else 'has also expired'}.",
            "next_step": ("Policy conflict (§4.2 says 30 days via store, §8.1 says 90 days legal warranty): do not "
                          "decide alone — explain both and hand off to a human. " if legal_ok else "")
            + "After 30 days the customer should use the manufacturer's warranty (6 months to 2 years, see the "
              "warranty certificate); the store can mediate on request."}


# ---------------------------------------------------------------- hand-off (Manual §7.3)
def open_ticket(ctx: Ctx, reason: str, summary: str, contact: str | None = None) -> dict:
    cur = ctx.conn.execute(
        "INSERT INTO tickets (session_id, reason, summary, contact, created_at) VALUES (?,?,?,?,?)",
        (ctx.session_id, reason, summary, contact, ctx.now.isoformat(timespec="seconds")))
    ctx.conn.commit()
    return {"ticket_id": f"EM-{cur.lastrowid:05d}", "status": "registered",
            "promise": "A team member will get back to the customer within 24 business hours."}
