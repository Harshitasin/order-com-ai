"""Pure-function tests for delay and return rules (no database, no LLM)."""
from datetime import date, datetime, timedelta

from order_assistant.services.business_rules import delay_info, return_eligibility

NOW = datetime.now()
HUB = [{"event_type": "HUB_DELAY", "note": "hub delay", "event_time": NOW}]
ITEMS = [{"product_name": "Shoes", "is_returnable": 1},
         {"product_name": "Earphones", "is_returnable": 0}]


def test_late_shipped_order_is_delayed_with_reason():
    d = delay_info({"status": "SHIPPED"},
                   {"expected_delivery": date.today() - timedelta(days=3)}, HUB)
    assert d == {"is_delayed": True, "days_late": 3, "likely_reason": "hub delay"}


def test_order_due_today_is_not_delayed():
    assert not delay_info({"status": "SHIPPED"}, {"expected_delivery": date.today()}, [])["is_delayed"]


def test_delivered_or_unshipped_orders_are_never_delayed():
    late = {"expected_delivery": date.today() - timedelta(days=9)}
    assert not delay_info({"status": "DELIVERED"}, late, [])["is_delayed"]
    assert not delay_info({"status": "PLACED"}, None, [])["is_delayed"]


def test_recently_delivered_order_is_returnable_except_flagged_items():
    r = return_eligibility({"status": "DELIVERED"}, {"delivered_at": NOW - timedelta(hours=20)}, ITEMS)
    assert r["eligible"] and r["non_returnable_items"] == ["Earphones"]


def test_return_window_expires():
    r = return_eligibility({"status": "DELIVERED"}, {"delivered_at": NOW - timedelta(days=12)}, ITEMS)
    assert not r["eligible"]


def test_undelivered_order_is_not_returnable():
    assert not return_eligibility({"status": "SHIPPED"}, None, ITEMS)["eligible"]


def test_order_with_only_non_returnable_items():
    only = [{"product_name": "Earphones", "is_returnable": 0}]
    assert not return_eligibility({"status": "DELIVERED"}, {"delivered_at": NOW}, only)["eligible"]
