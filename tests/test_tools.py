from datetime import datetime

import pytest

from emporio import config, db
from emporio.policies.retriever import build_chunks, get_index
from emporio.tools import orders, payments, products, store
from emporio.tools.common import Ctx, brl


@pytest.fixture()
def ctx():
    return Ctx(conn=db.build_db(":memory:"), now=datetime(2026, 3, 20, 10, 30, tzinfo=config.TZ))


def test_brl_format():
    assert brl(2199) == "R$ 2.199,00"
    assert brl(1234567.5) == "R$ 1.234.567,50"


# ---------------------------------------------------------------- products
def test_budget_search_excludes_out_of_stock(ctx):
    r = products.search_products(ctx, category="violões", max_price=1000)
    names = [p["name"] for p in r["products"]]
    assert r["total_matches"] > 0
    assert not any("GF-3D" in n for n in names)  # stock 0
    assert all(p["availability"] == "in_stock" for p in r["products"])


def test_takamine_gd20_price(ctx):
    r = products.get_product(ctx, "Takamine GD20")
    assert r["found"] and r["product"]["list_price"] == "R$ 2.199,00"
    assert "promotion" not in r["product"]  # its only promotion is inactive
    assert r["product"]["pix_price"] == "R$ 2.089,05"


def test_ambiguous_name_asks_back(ctx):
    r = products.get_product(ctx, "takamine")
    assert r["ambiguous"] and len(r["candidates"]) == 4


def test_discontinued_with_stock_is_not_available(ctx):
    r = products.get_product(ctx, "Ibanez Bass 2X")
    assert r["product"]["availability"] == "discontinued" and r["product"]["units_in_stock"] == 0
    assert r["alternatives"]


def test_coming_soon_not_available(ctx):
    r = products.get_product(ctx, "Kala KA-ABP-CTG")
    assert r["product"]["availability"] == "coming_soon"


def test_only_active_promotions_and_no_pix_stack(ctx):
    r = products.get_product(ctx, "Ohana CK-20")["product"]  # 20% active
    assert r["promotion"]["promo_price"] == "R$ 439,20"
    assert "pix_price" not in r
    old = products.get_product(ctx, "Martin D-28")["product"]  # inactive promos only
    assert "promotion" not in old


def test_unknown_product(ctx):
    assert products.get_product(ctx, "saxofone alto Selmer")["found"] is False


# ---------------------------------------------------------------- store / payments / shipping
def test_opening_hours(ctx):
    assert store.is_open_now(ctx)["is_open"]  # Friday 10:30
    ctx.now = datetime(2026, 3, 21, 14, 0, tzinfo=config.TZ)  # Saturday after 13:00
    r = store.is_open_now(ctx)
    assert not r["is_open"] and "Monday" in r["next_opening"]


def test_installment_rules(ctx):
    r = payments.payment_options(ctx, 600)
    assert r["max_installments_no_interest"] == 6  # 7x would be < R$100
    assert r["pix"]["price"] == "R$ 570,00"
    assert payments.payment_options(ctx, 2400)["max_installments_no_interest"] == 12
    assert "No extra PIX" in payments.payment_options(ctx, 439.2, True)["pix"]["note"]
    assert payments.payment_options(ctx, 100)["max_installments_no_interest"] == 2


def test_shipping(ctx):
    assert payments.shipping_quote(ctx, "Campo Grande", 900)["fee"] == "free"
    assert payments.shipping_quote(ctx, "campo grande", 300)["fee"] == "R$ 35,00"
    assert "options" in payments.shipping_quote(ctx, "Dourados", 900)


# ---------------------------------------------------------------- orders & privacy
def test_order_requires_verification(ctx):
    assert orders.get_order(ctx, 8)["verified"] is False
    assert orders.get_order(ctx, 8, "wrong@x.com")["verified"] is False
    assert orders.get_order(ctx, 999, "wrong@x.com") == orders.get_order(ctx, 8, "wrong@x.com")  # no existence leak


def test_order_after_verification(ctx):
    email = ctx.conn.execute("SELECT c.email FROM orders o JOIN customers c USING(customer_id) WHERE order_id=8").fetchone()[0]
    r = orders.get_order(ctx, 8, email)
    assert r["tracking_code"] == "BRJL5544332BR" and "shipped" in r["status"]
    assert orders.get_order(ctx, 9) == orders.get_order(ctx, 9, None)  # other customer's order still locked


def test_shared_email_does_not_unlock_wrong_order(ctx):
    # customers 11 and 43 share an e-mail; verification is per order owner, so access stays scoped to the owner.
    r = orders.verify_customer(ctx, 10, "bruno.martins@jmail.com")  # order 10 belongs to customer 11
    assert r["verified"]
    assert ctx.verified_customers == {11}


def test_cancelled_order_reason(ctx):
    email = ctx.conn.execute("SELECT c.email FROM orders o JOIN customers c USING(customer_id) WHERE order_id=18").fetchone()[0]
    assert "estoque" in orders.get_order(ctx, 18, email)["cancellation_reason"]


# ---------------------------------------------------------------- returns
def _verify(ctx, oid):
    email = ctx.conn.execute("SELECT c.email FROM orders o JOIN customers c USING(customer_id) WHERE order_id=?", (oid,)).fetchone()[0]
    orders.verify_customer(ctx, oid, email)


def test_regret_inside_window(ctx):
    _verify(ctx, 8)  # shipped -> not returnable yet
    assert orders.evaluate_return(ctx, 8, "regret")["eligible"] is None
    _verify(ctx, 7)  # delivered, estimated 2026-02-17
    ctx.now = datetime(2026, 2, 20, 10, tzinfo=config.TZ)
    assert orders.evaluate_return(ctx, 7, "regret")["eligible"] is True


def test_regret_outside_window(ctx):
    _verify(ctx, 7)
    r = orders.evaluate_return(ctx, 7, "regret")  # now = 2026-03-20, 31 days after
    assert r["eligible"] is False and r["days_since_receipt"] == 31


def test_defect_30_and_legal_90(ctx):
    _verify(ctx, 7)
    ctx.now = datetime(2026, 3, 10, tzinfo=config.TZ)  # 21 days
    assert orders.evaluate_return(ctx, 7, "defect")["eligible"] is True
    ctx.now = datetime(2026, 4, 20, tzinfo=config.TZ)  # 62 days: store window gone, legal warranty remains
    r = orders.evaluate_return(ctx, 7, "defect")
    assert r["eligible"] is False and "still applies" in r["legal_warranty"] and "human" in r["next_step"]


def test_return_blocked_without_verification(ctx):
    assert orders.evaluate_return(ctx, 7, "regret")["verified"] is False


def test_ticket(ctx):
    t = orders.open_ticket(ctx, "complaint", "Late delivery")
    assert t["ticket_id"].startswith("EM-") and "24" in t["promise"]


# ---------------------------------------------------------------- policy retrieval
def test_policy_chunks_cover_manual():
    sections = {c.section for c in build_chunks()}
    assert {"2", "3.1", "4.1", "4.2", "5.1", "5.2", "5.3", "6.2", "7.1", "8.1", "9"} <= sections


@pytest.mark.parametrize("question,expected", [
    ("me arrependi da compra, posso devolver?", "4.1"),
    ("qual o horário no sábado?", "2"),
    ("posso parcelar em 12x?", "3.1"),
    ("o desconto do pix vale em promoção?", "6.2"),
    ("a garantia cobre queda?", "8.3"),
    ("vocês vendem cordas?", "1"),
])
def test_policy_retrieval_top3(question, expected):
    assert expected in [c.section for _, c in get_index().search(question, 3)]


def test_policy_offtopic_returns_nothing():
    assert get_index().search("qual a capital da França") == []


def test_verify_rejects_blank_input(ctx):
    assert orders.verify_customer(ctx, 0, "")["verified"] is False
    assert orders.verify_customer(ctx, 7, "  ")["verified"] is False
