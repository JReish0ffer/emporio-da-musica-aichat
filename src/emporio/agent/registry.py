"""Tool registry: JSON schemas shown to the LLM + safe dispatch."""
from __future__ import annotations

import json
from typing import Any, Callable

from ..policies.retriever import search_policies
from ..tools import orders, payments, products, store
from ..tools.common import Ctx


def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required or []}}}


_S, _N, _B = {"type": "string"}, {"type": "number"}, {"type": "boolean"}

SCHEMAS = [
    _fn("search_products",
        "Search the live catalog with filters. Use for 'what do you have', budgets, types. Returns price, stock and "
        "active promotion. Never quote prices/stock from memory.",
        {"query": {**_S, "description": "Free-text keywords, e.g. 'folk', 'tenor', brand"},
         "category": {**_S, "description": "Violões, Guitarras, Baixos, Ukuleles, Baterias e Percussão, Teclados e Pianos, ..."},
         "max_price": {**_N, "description": "BRL, compared with the effective (promo) price"},
         "min_price": _N,
         "string_type": {"type": "string", "enum": ["nylon", "steel"]},
         "electric": {**_B, "description": "true = with built-in electronics (eletroacústico)"},
         "color": _S,
         "only_available": {**_B, "description": "default true; set false to also see out-of-stock items"},
         "limit": {"type": "integer"}}),
    _fn("get_product",
        "Look up ONE product by name/model (fuzzy), e.g. 'Takamine GD20'. Gives price, stock, specs, promotion, and "
        "alternatives if unavailable. May return ambiguous candidates: then ask the customer which one.",
        {"name": _S}, ["name"]),
    _fn("list_categories", "Categories and how many products are available in each.", {}),
    _fn("active_promotions", "All promotions that are active right now.", {}),
    _fn("search_policies",
        "Search the store policy manual (returns, exchange, warranty, payment, installments, shipping, tracking, "
        "promotion rules, privacy, service guidelines). Use for any 'how does X work / what is the rule' question.",
        {"question": _S}, ["question"]),
    _fn("store_info", "Address, phones, e-mail, opening hours, what the store sells.", {}),
    _fn("is_open_now", "Whether the store is open at this moment and when it opens next.", {}),
    _fn("payment_options",
        "Exact installment table and PIX price for an amount. Use whenever the customer asks about parcelas/PIX for a value.",
        {"amount": {**_N, "description": "Total in BRL"},
         "has_active_promotion": {**_B, "description": "true if the amount is already a promotional price"}}, ["amount"]),
    _fn("shipping_quote",
        "Shipping fee/time for a destination city and order total.",
        {"city": _S, "order_total": _N, "large_item": {**_B, "description": "drums, digital piano, double bass"}},
        ["city", "order_total"]),
    _fn("verify_customer",
        "Verify a customer for order access: needs the order number and the e-mail OR phone registered on it.",
        {"order_id": {"type": "integer"}, "email_or_phone": _S}, ["order_id", "email_or_phone"]),
    _fn("get_order",
        "Order status, items, total, tracking code, estimated delivery. Requires verification (pass email_or_phone, "
        "or call verify_customer first).",
        {"order_id": {"type": "integer"}, "email_or_phone": _S}, ["order_id"]),
    _fn("evaluate_return",
        "Apply the return/exchange rules to a verified delivered order. reason: regret | defect | preference.",
        {"order_id": {"type": "integer"}, "reason": {"type": "string", "enum": ["regret", "defect", "preference"]}},
        ["order_id", "reason"]),
    _fn("open_ticket",
        "Register a hand-off to a human (complaint, cancellation/refund request, anything you cannot resolve). "
        "Customer is promised an answer within 24 business hours.",
        {"reason": _S, "summary": {**_S, "description": "Self-contained summary for the human attendant"},
         "contact": {**_S, "description": "Customer name/phone/e-mail if given"},
         "ticket_id": {**_S, "description": "Existing ticket id (e.g. EM-00001) to add information instead of opening a new one"}},
        ["reason", "summary"]),
]

_IMPL: dict[str, Callable[..., Any]] = {
    "search_products": products.search_products, "get_product": products.get_product,
    "list_categories": products.list_categories, "active_promotions": products.active_promotions,
    "search_policies": lambda ctx, question: search_policies(ctx, question),
    "store_info": store.store_info, "is_open_now": store.is_open_now,
    "payment_options": payments.payment_options, "shipping_quote": payments.shipping_quote,
    "verify_customer": orders.verify_customer, "get_order": orders.get_order,
    "evaluate_return": orders.evaluate_return, "open_ticket": orders.open_ticket,
}


def dispatch(ctx: Ctx, name: str, arguments: str | dict) -> str:
    """Run a tool; always returns a JSON string (errors included) so the LLM can recover."""
    try:
        args = json.loads(arguments) if isinstance(arguments, str) and arguments.strip() else (arguments or {})
        if name not in _IMPL:
            return json.dumps({"error": f"unknown tool {name}"})
        return json.dumps(_IMPL[name](ctx, **args), ensure_ascii=False, default=str)
    except TypeError as e:
        return json.dumps({"error": f"bad arguments: {e}"})
    except Exception as e:  # keep the conversation alive; the model apologises/hands off
        return json.dumps({"error": f"tool failed: {type(e).__name__}: {e}"})
