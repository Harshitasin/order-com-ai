"""seed_data.py - generates FAKE test data for the shop database. Re-runnable.

Before running:   pip install -e ".[dev]"      (installs faker, pymysql, werkzeug)
Run (from the project root):   python scripts/seed_data.py

What you get: 20 fake customers, 3 policies, and 100 orders:
9 hand-made edge cases (late order, expired return window, non-returnable item,
orders of customer 2 used for isolation tests) + 91 random ones.
Dates are relative to "now", so re-run it if the integration tests start failing.

NOTE: This script connects as root because assistant_ro has no INSERT
permission (and must never have it). Root is for setup only; the app code
must never use root.
"""
import os
import random
from datetime import datetime, timedelta
from getpass import getpass

import pymysql
from faker import Faker
from werkzeug.security import generate_password_hash

random.seed(42)          # same data on every run (reproducible tests)
Faker.seed(42)
fake = Faker("en_IN")
NOW = datetime.now().replace(microsecond=0)

PAYMENTS = ["UPI", "CARD", "COD", "NETBANKING"]
CARRIERS = ["BlueDart", "Delhivery", "Ecom Express", "XpressBees"]
CITIES = ["Lucknow", "Delhi", "Mumbai", "Kanpur", "Jaipur", "Pune"]
PRODUCTS = [
    ("Running Shoes", 2499), ("Cotton T-Shirt", 599), ("Bluetooth Speaker", 1799),
    ("Backpack", 1299), ("Water Bottle", 399), ("Denim Jacket", 2999),
    ("Wireless Mouse", 699), ("Yoga Mat", 899),
]


def ago(days=0, hours=0):
    return NOW - timedelta(days=days, hours=hours)


# ---------------------------------------------------------------- helpers
def wipe(cur):
    """Empty all tables so the script can be re-run safely."""
    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    for t in ["shipment_events", "refunds", "shipments", "order_items",
              "orders", "customers", "policies", "chat_audit_log"]:
        cur.execute(f"TRUNCATE TABLE {t}")
    cur.execute("SET FOREIGN_KEY_CHECKS=1")


def seed_policies(cur):
    rows = [
        ("return_policy", "Items can be returned within 7 days of delivery. Hygiene-sealed items (such as earphones) are not returnable."),
        ("refund_timeline", "Once a refund is approved, it reaches the original payment method in 5-7 working days."),
        ("cancellation_policy", "Orders can be cancelled free of charge before they ship. After shipping, cancellation is not possible; please return the item instead."),
    ]
    cur.executemany("INSERT INTO policies (policy_key, policy_text) VALUES (%s,%s)", rows)


def seed_customers(cur):
    pw = generate_password_hash("Test@1234")      # same password for everyone, testing only
    rows = [
        ("Test Customer One", "test1@example.com", pw),   # customer_id = 1
        ("Test Customer Two", "test2@example.com", pw),   # customer_id = 2
    ]
    for _ in range(18):
        rows.append((fake.name(), fake.unique.email(), pw))
    cur.executemany(
        "INSERT INTO customers (name, email, password_hash) VALUES (%s,%s,%s)", rows)


def add_order(cur, oid, cust, status, placed_at, items,
              ship=None, events=(), refund=None):
    """
    items  : [(product_name, qty, price, is_returnable), ...]
    ship   : (expected_delivery_date, delivered_at_or_None) or None
    events : [(event_time, location, event_type, note), ...]
    refund : (status, initiated_at, expected_by_date, mode) or None
    """
    total = sum(qty * price for _, qty, price, _ in items)
    cur.execute(
        "INSERT INTO orders (order_id, customer_id, status, placed_at, total_amount, payment_method) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (oid, cust, status, placed_at, total, random.choice(PAYMENTS)))

    for name, qty, price, returnable in items:
        cur.execute(
            "INSERT INTO order_items (order_id, product_name, qty, price, is_returnable) "
            "VALUES (%s,%s,%s,%s,%s)", (oid, name, qty, price, returnable))

    if ship:
        expected, delivered_at = ship
        cur.execute(
            "INSERT INTO shipments (order_id, carrier, tracking_no, expected_delivery, delivered_at) "
            "VALUES (%s,%s,%s,%s,%s)",
            (oid, random.choice(CARRIERS), f"TRK{random.randint(10**9, 10**10 - 1)}",
             expected, delivered_at))
        shipment_id = cur.lastrowid               # id of the shipment just inserted
        for t, loc, etype, note in events:
            cur.execute(
                "INSERT INTO shipment_events (shipment_id, event_time, location, event_type, note) "
                "VALUES (%s,%s,%s,%s,%s)", (shipment_id, t, loc, etype, note))

    if refund:
        r_status, r_init, r_expected, r_mode = refund
        cur.execute(
            "INSERT INTO refunds (order_id, amount, status, initiated_at, expected_by, refund_mode) "
            "VALUES (%s,%s,%s,%s,%s,%s)", (oid, total, r_status, r_init, r_expected, r_mode))


# ---------------------------------------------------- hand-made edge cases
def seed_edge_cases(cur):
    shoes = ("Running Shoes", 1, 2499, True)
    tee = ("Cotton T-Shirt", 2, 599, True)
    earphones = ("Earphones (hygiene sealed)", 1, 999, False)   # not returnable

    # 100001: delivered yesterday -> RETURN ELIGIBLE
    add_order(cur, "ORD-100001", 1, "DELIVERED", ago(5), [shoes],
              ship=(ago(1).date(), ago(hours=20)),
              events=[(ago(4), "Lucknow", "PICKED_UP", "Picked up from seller"),
                      (ago(3), "Kanpur", "IN_TRANSIT", "Arrived at transit hub"),
                      (ago(hours=20), "Lucknow", "DELIVERED", "Delivered to customer")])

    # 100002: delivered 12 days ago -> RETURN WINDOW EXPIRED
    add_order(cur, "ORD-100002", 1, "DELIVERED", ago(18), [tee],
              ship=(ago(13).date(), ago(12)),
              events=[(ago(17), "Delhi", "PICKED_UP", "Picked up from seller"),
                      (ago(12), "Lucknow", "DELIVERED", "Delivered to customer")])

    # 100003: DELAYED (3 days late) + HUB_DELAY event
    add_order(cur, "ORD-100003", 1, "SHIPPED", ago(8), [shoes, tee],
              ship=((NOW - timedelta(days=3)).date(), None),
              events=[(ago(7), "Delhi", "PICKED_UP", "Picked up from seller"),
                      (ago(5), "Kanpur", "IN_TRANSIT", "Arrived at transit hub"),
                      (ago(4), "Kanpur", "HUB_DELAY", "Delay at hub due to high volume")])

    # 100004: delivered, but one item is NON-RETURNABLE
    add_order(cur, "ORD-100004", 1, "DELIVERED", ago(6), [earphones, tee],
              ship=(ago(3).date(), ago(2)),
              events=[(ago(5), "Mumbai", "PICKED_UP", "Picked up from seller"),
                      (ago(2), "Lucknow", "DELIVERED", "Delivered to customer")])

    # 100005: CANCELLED + refund PROCESSING
    add_order(cur, "ORD-100005", 1, "CANCELLED", ago(4), [shoes],
              refund=("PROCESSING", ago(3), (NOW + timedelta(days=3)).date(), "UPI"))

    # 100006: due for delivery today (OUT_FOR_DELIVERY)
    add_order(cur, "ORD-100006", 1, "OUT_FOR_DELIVERY", ago(4), [tee],
              ship=(NOW.date(), None),
              events=[(ago(3), "Jaipur", "PICKED_UP", "Picked up from seller"),
                      (ago(1), "Lucknow", "IN_TRANSIT", "Arrived at local hub"),
                      (ago(hours=3), "Lucknow", "OUT_FOR_DELIVERY", "Out for delivery")])

    # 100007: just PLACED, no shipment exists yet
    add_order(cur, "ORD-100007", 1, "PLACED", ago(hours=5), [shoes])

    # ---- customer 2's orders: targets for the ISOLATION TESTS ----
    # 100200: customer 2's delayed order (customer 1 must NEVER see this)
    add_order(cur, "ORD-100200", 2, "SHIPPED", ago(9), [tee],
              ship=((NOW - timedelta(days=2)).date(), None),
              events=[(ago(8), "Pune", "PICKED_UP", "Picked up from seller"),
                      (ago(4), "Pune", "WEATHER_DELAY", "Heavy rain, deliveries paused")])

    add_order(cur, "ORD-100201", 2, "DELIVERED", ago(10), [shoes],
              ship=(ago(5).date(), ago(4)),
              events=[(ago(9), "Pune", "PICKED_UP", "Picked up from seller"),
                      (ago(4), "Delhi", "DELIVERED", "Delivered to customer")])

    # Ideas for extra edge cases (not included yet):
    #   1. An order with an ADDRESS_ISSUE event
    #   2. An order whose refund is COMPLETED


# ----------------------------------------------------------- random orders
def add_random_order(cur, oid, cust):
    status = random.choice(["PLACED", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY",
                            "DELIVERED", "DELIVERED", "DELIVERED", "CANCELLED"])
    day_range = {"PLACED": (0, 1), "PACKED": (0, 1), "SHIPPED": (3, 6),
                 "OUT_FOR_DELIVERY": (4, 6), "DELIVERED": (8, 30), "CANCELLED": (1, 20)}[status]
    placed = ago(random.randint(*day_range), random.randint(0, 23))

    items = [(name, random.randint(1, 2), price, random.random() > 0.1)
             for name, price in random.sample(PRODUCTS, random.randint(1, 3))]

    ship, events, refund = None, [], None
    if status in ("SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"):
        expected = (placed + timedelta(days=random.randint(4, 7))).date()
        shipped_at = placed + timedelta(days=1)
        events = [
            (shipped_at, random.choice(CITIES), "PICKED_UP", "Picked up from seller"),
            (shipped_at + timedelta(days=1), random.choice(CITIES), "IN_TRANSIT", "Arrived at transit hub"),
        ]
        if random.random() < 0.3:
            events.append((shipped_at + timedelta(days=1, hours=6), random.choice(CITIES),
                           "HUB_DELAY", "Delay at hub due to high volume"))
        delivered_at = None
        if status == "DELIVERED":
            delivered_at = placed + timedelta(days=random.randint(3, 7))
            events.append((delivered_at, random.choice(CITIES), "DELIVERED", "Delivered to customer"))
        ship = (expected, delivered_at)

    if status == "CANCELLED" and random.random() < 0.7:
        refund = (random.choice(["PROCESSING", "COMPLETED"]), placed + timedelta(days=1),
                  (placed + timedelta(days=6)).date(), random.choice(["UPI", "CARD", "WALLET"]))
    elif status == "DELIVERED" and random.random() < 0.1:
        refund = ("INITIATED", ship[1] + timedelta(days=1),
                  (ship[1] + timedelta(days=7)).date(), "UPI")

    add_order(cur, oid, cust, status, placed, items, ship, events, refund)


# -------------------------------------------------------------------- main
def main():
    # Root password: MYSQL_ROOT_PASSWORD env var (Docker) or an interactive prompt (local).
    pw = os.getenv("MYSQL_ROOT_PASSWORD") or getpass("MySQL root password: ")
    conn = pymysql.connect(host=os.getenv("DB_HOST", "127.0.0.1"),
                           port=int(os.getenv("DB_PORT", "3306")),
                           user="root", password=pw,
                           database=os.getenv("DB_NAME", "shop"))
    try:
        with conn.cursor() as cur:
            wipe(cur)
            seed_policies(cur)
            seed_customers(cur)
            seed_edge_cases(cur)
            for i in range(91):                       # 9 edge + 91 random = 100 orders
                add_random_order(cur, f"ORD-{100300 + i}", random.randint(1, 20))
        conn.commit()

        with conn.cursor() as cur:
            for t in ["customers", "orders", "order_items", "shipments",
                      "shipment_events", "refunds", "policies"]:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                print(f"{t:16} {cur.fetchone()[0]}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
