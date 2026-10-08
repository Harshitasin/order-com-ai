"""business_rules.py - facts are computed HERE, in plain Python, not by the LLM.

Why: an LLM can be wrong about dates and arithmetic. If "is this order late?"
or "can it still be returned?" is computed in code, the LLM only has to
*explain* a result, which makes answers testable and measurable.

These functions are pure (no DB calls), so they are trivial to unit-test.
"""
from datetime import date, datetime, timedelta

# Keep in sync with the 'return_policy' text in the policies table.
RETURN_WINDOW_DAYS = 7

# Shipment event types that explain a delay.
DELAY_EVENT_TYPES = ("HUB_DELAY", "WEATHER_DELAY", "ADDRESS_ISSUE", "DELIVERY_ATTEMPT_FAILED")


def delay_info(order, shipment, events):
    """
    Decide whether an order is delayed and, if so, why.

    order    : dict row from orders
    shipment : dict row from shipments, or None (e.g. order not shipped yet)
    events   : list of shipment_events rows, sorted by event_time ASCENDING
    """
    not_delayed = {"is_delayed": False, "days_late": 0, "likely_reason": None}

    # Nothing to be late about if the order is finished or not shipped yet.
    if shipment is None or order["status"] in ("DELIVERED", "CANCELLED"):
        return not_delayed

    expected = shipment["expected_delivery"]       # a DATE (no time part)
    if expected is None:
        return not_delayed

    # date.today() > expected means "strictly after the expected date".
    # An order due TODAY is not late yet (same rule as SQL's CURDATE()).
    today = date.today()
    if today <= expected:
        return not_delayed

    # Latest event that explains a delay (events are oldest -> newest).
    reasons = [e for e in events if e["event_type"] in DELAY_EVENT_TYPES]
    reason = reasons[-1]["note"] if reasons else "No specific reason recorded"

    return {
        "is_delayed": True,
        "days_late": (today - expected).days,
        "likely_reason": reason,
    }


def return_eligibility(order, shipment, items):
    """
    Decide whether the customer can still return this order.

    items : list of order_items rows (needs product_name, is_returnable)
    """
    # Only delivered orders can be returned.
    if order["status"] != "DELIVERED" or shipment is None or shipment["delivered_at"] is None:
        return {"eligible": False, "reason": "Order has not been delivered, so it cannot be returned."}

    deadline = shipment["delivered_at"] + timedelta(days=RETURN_WINDOW_DAYS)
    if datetime.now() > deadline:
        return {
            "eligible": False,
            "reason": f"Return window of {RETURN_WINDOW_DAYS} days ended on {deadline:%d %b %Y}.",
        }

    non_returnable = [i["product_name"] for i in items if not i["is_returnable"]]
    if items and len(non_returnable) == len(items):
        return {"eligible": False, "reason": "All items in this order are non-returnable."}

    days_left = (deadline - datetime.now()).days
    return {
        "eligible": True,
        "deadline": f"{deadline:%d %b %Y}",
        "days_left": days_left,
        "non_returnable_items": non_returnable,   # partial returns: these items stay out
    }
