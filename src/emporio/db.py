"""CSV -> SQLite loading, light cleaning, and a data-quality report."""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE categories (category_id INTEGER PRIMARY KEY, name TEXT, description TEXT);
CREATE TABLE customers  (customer_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, email TEXT, city TEXT);
CREATE TABLE products   (product_id INTEGER PRIMARY KEY, price_brl REAL NOT NULL, name TEXT NOT NULL,
                         category_id INTEGER REFERENCES categories, description TEXT,
                         stock_quantity INTEGER NOT NULL, status TEXT NOT NULL, specs TEXT, created_at TEXT);
CREATE TABLE promotions (promotion_id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products,
                         discount_percent REAL, description TEXT, is_active INTEGER);
CREATE TABLE orders     (order_id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers,
                         order_date TEXT, status TEXT, total_brl REAL, payment_method TEXT,
                         tracking_code TEXT, estimated_delivery TEXT, notes TEXT);
CREATE TABLE order_items(order_id INTEGER REFERENCES orders, product_id INTEGER REFERENCES products,
                         quantity INTEGER);
-- runtime tables
CREATE TABLE sessions   (session_id TEXT PRIMARY KEY, created_at TEXT, verified_customers TEXT DEFAULT '[]');
CREATE TABLE messages   (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT, content TEXT,
                         meta TEXT, created_at TEXT);
CREATE TABLE tickets    (ticket_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, reason TEXT,
                         summary TEXT, contact TEXT, created_at TEXT, status TEXT DEFAULT 'open');
"""

_TABLES = {
    "categories": ("categories", ["category_id", "name", "description"]),
    "customers": ("customers", ["customer_id", "name", "phone", "email", "city"]),
    "products": ("products", ["product_id", "price_brl", "name", "category_id", "description",
                              "stock_quantity", "status", "specs", "created_at"]),
    "promotions": ("promotions", ["promotion_id", "product_id", "discount_percent", "description", "is_active"]),
    "orders": ("orders", ["order_id", "customer_id", "order_date", "status", "total_brl", "payment_method",
                          "tracking_code", "estimated_delivery", "notes"]),
    "order_items": ("order_items", ["order_id", "product_id", "quantity"]),
}


def _read_csv(name: str) -> list[dict]:
    path = config.DATA_DIR / f"{config.CSV_PREFIX}{name}.csv"
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    # Cleaning: strip whitespace, empty string -> NULL.
    return [{k: (v.strip() if isinstance(v, str) and v.strip() != "" else None) for k, v in r.items()} for r in rows]


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or config.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def build_db(path: Path | str | None = None) -> sqlite3.Connection:
    """(Re)create the database from the CSVs. Runtime tables start empty."""
    p = Path(path or config.DB_PATH)
    if str(p) != ":memory:" and p.exists():
        p.unlink()
    conn = connect(p)
    conn.executescript(SCHEMA)
    for csv_name, (table, cols) in _TABLES.items():
        rows = _read_csv(csv_name)
        conn.executemany(
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [[r[c] for c in cols] for r in rows],
        )
    conn.commit()
    return conn


def get_conn() -> sqlite3.Connection:
    """Open the DB, building it from the CSVs on first run."""
    if not config.DB_PATH.exists():
        return build_db()
    return connect()


def quality_report(conn: sqlite3.Connection) -> list[str]:
    """Known data problems. Surfaced (not silently 'fixed') and documented in the README."""
    q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
    issues: list[str] = []
    for r in q("SELECT product_id, name FROM products WHERE status='active' AND stock_quantity=0"):
        issues.append(f"product {r[0]} '{r[1]}' is active but has zero stock")
    for r in q("SELECT product_id, name, stock_quantity, status FROM products "
               "WHERE status!='active' AND stock_quantity>0"):
        issues.append(f"product {r[0]} '{r[1]}' is {r[3]} but shows stock {r[2]} (status wins over stock)")
    for r in q("""SELECT o.order_id, o.total_brl, SUM(p.price_brl*i.quantity) s FROM orders o
                  JOIN order_items i USING(order_id) JOIN products p USING(product_id)
                  GROUP BY o.order_id HAVING ABS(o.total_brl - s) > 0.01"""):
        issues.append(f"order {r[0]}: total_brl {r[1]} != sum of current item prices {r[2]:.2f} (total_brl wins)")
    for r in q("SELECT email, GROUP_CONCAT(customer_id) FROM customers GROUP BY email HAVING COUNT(*)>1"):
        issues.append(f"customers {r[1]} share e-mail {r[0]} (e-mail alone cannot identify a customer)")
    for r in q("""SELECT c.name FROM categories c LEFT JOIN products p USING(category_id)
                  GROUP BY c.category_id HAVING COUNT(p.product_id)=0"""):
        issues.append(f"category '{r[0]}' has no products")
    for r in q("""SELECT DISTINCT p.product_id, p.name FROM order_items i JOIN products p USING(product_id)
                  WHERE p.status='coming_soon'"""):
        issues.append(f"product {r[0]} '{r[1]}' is coming_soon yet appears in orders")
    for r in q("SELECT product_id, COUNT(*) FROM promotions WHERE is_active=1 GROUP BY product_id HAVING COUNT(*)>1"):
        issues.append(f"product {r[0]} has {r[1]} active promotions (highest discount is used)")
    for (spec,) in q("SELECT specs FROM products"):
        try:
            json.loads(spec or "{}")
        except json.JSONDecodeError:
            issues.append("invalid specs JSON found")
    return issues


if __name__ == "__main__":
    c = build_db()
    for table in _TABLES:
        print(f"{table:12s} {c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]} rows")
    print("\nData quality notes:")
    for i in quality_report(c):
        print(" -", i)
