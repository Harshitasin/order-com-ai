"""Needs MySQL running and seeded (python scripts/seed_data.py).

Seed dates are relative to when you seeded. A week later ORD-100001's return
window will have closed and its test will fail - re-run the seed script.
"""
import pytest

from order_assistant.core.db import query
from order_assistant.services.tools import (
    NOT_FOUND, check_return_eligibility, get_order_status, get_refund_status,
)

pytestmark = pytest.mark.integration


def test_delayed_order_with_hub_reason():
    d = get_order_status("ORD-100003", 1)["delay"]
    assert d["is_delayed"] and d["days_late"] >= 1 and "hub" in d["likely_reason"].lower()


def test_order_due_today_is_not_delayed():
    assert not get_order_status("ORD-100006", 1)["delay"]["is_delayed"]


def test_placed_order_has_no_shipment():
    r = get_order_status("ORD-100007", 1)
    assert r["shipment"] is None and not r["delay"]["is_delayed"]


def test_return_rules():
    assert check_return_eligibility("ORD-100001", 1)["eligible"]
    assert not check_return_eligibility("ORD-100002", 1)["eligible"]
    r = check_return_eligibility("ORD-100004", 1)
    assert r["eligible"] and any("Earphones" in n for n in r["non_returnable_items"])


def test_refund_processing():
    assert get_refund_status("ORD-100005", 1)["refunds"][0]["status"] == "PROCESSING"


def test_foreign_missing_and_malformed_ids_look_identical():
    foreign = get_order_status("ORD-100200", 1)       # belongs to customer 2
    missing = get_order_status("ORD-999999", 1)
    assert foreign == missing == NOT_FOUND
    assert get_order_status("ORD-1' OR '1'='1", 1) == NOT_FOUND


def test_zero_cross_customer_leakage():
    """Seed of the leakage-rate metric: every viewer tries every order that is not theirs."""
    orders = query("SELECT order_id, customer_id FROM orders")
    leaks = [(viewer, o["order_id"])
             for viewer in (1, 2, 3)
             for o in orders
             if o["customer_id"] != viewer
             and get_order_status(o["order_id"], viewer) != NOT_FOUND]
    assert leaks == []
