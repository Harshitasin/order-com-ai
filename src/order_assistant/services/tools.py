"""tools.py - the ONLY functions the LLM is allowed to trigger.

Design rules (this is the security model of the whole project):
  1. customer_id is NEVER an argument the LLM controls. dispatch() injects it
     from the caller (the API layer), so the model cannot ask for "customer 2".
  2. Every query that touches an order goes through _get_owned_order(), which
     filters on BOTH order_id and customer_id in SQL.
  3. "Order does not exist" and "order belongs to someone else" return the
     exact same NOT_FOUND object, so nothing leaks by comparing responses.
  4. All DB access goes through db.query() (parameterized, SELECT-only).
"""
import re
import traceback

from order_assistant.core.db import query
from order_assistant.services.business_rules import delay_info, return_eligibility

ORDER_ID_RE = re.compile(r"^ORD-\d{4,10}$")
ALLOWED_POLICIES = ("return_policy", "refund_timeline", "cancellation_policy")

NOT_FOUND = {"error": "No order with this ID was found in your account."}


# ----------------------------------------------------------------- helpers
def _get_owned_order(order_id, customer_id):
    """Return the order row only if it belongs to customer_id, else None."""
    if not isinstance(order_id, str) or not ORDER_ID_RE.match(order_id):
        return None                                  # bad format: never reaches the DB
    rows = query(
        "SELECT * FROM orders WHERE order_id = %s AND customer_id = %s",
        (order_id, customer_id),
    )
    return rows[0] if rows else None


def _get_shipment(order_id):
    rows = query(
        "SELECT shipment_id, carrier, tracking_no, expected_delivery, delivered_at "
        "FROM shipments WHERE order_id = %s",
        (order_id,),
    )
    return rows[0] if rows else None                 # None = not shipped yet


def _get_events(shipment):
    if shipment is None:
        return []
    return query(
        "SELECT event_time, location, event_type, note FROM shipment_events "
        "WHERE shipment_id = %s ORDER BY event_time ASC",
        (shipment["shipment_id"],),
    )


def _get_items(order_id):
    return query(
        "SELECT product_name, qty, price, is_returnable FROM order_items WHERE order_id = %s",
        (order_id,),
    )


# ------------------------------------------------------------------- tools
def get_order_status(order_id, customer_id):
    order = _get_owned_order(order_id, customer_id)
    if order is None:
        return NOT_FOUND

    items = _get_items(order_id)
    shipment = _get_shipment(order_id)
    events = _get_events(shipment)

    return {
        # customer_id is dropped: the model does not need it
        "order": {k: v for k, v in order.items() if k != "customer_id"},
        "items": items,
        "shipment": shipment,
        "recent_events": events[-5:],                # last 5 events are enough context
        "delay": delay_info(order, shipment, events),
    }


def get_refund_status(order_id, customer_id):
    if _get_owned_order(order_id, customer_id) is None:
        return NOT_FOUND
    refunds = query(
        "SELECT amount, status, initiated_at, expected_by, refund_mode "
        "FROM refunds WHERE order_id = %s ORDER BY initiated_at",
        (order_id,),
    )
    return {"refunds": refunds} if refunds else {"message": "No refund has been initiated for this order."}


def check_return_eligibility(order_id, customer_id):
    order = _get_owned_order(order_id, customer_id)
    if order is None:
        return NOT_FOUND
    return return_eligibility(order, _get_shipment(order_id), _get_items(order_id))


def list_recent_orders(customer_id, limit=5):
    limit = max(1, min(int(limit), 20))              # clamp so nobody dumps the table
    return {
        "orders": query(
            "SELECT order_id, status, placed_at, total_amount FROM orders "
            "WHERE customer_id = %s ORDER BY placed_at DESC LIMIT %s",
            (customer_id, limit),
        )
    }


def get_policy(policy_key):
    if policy_key not in ALLOWED_POLICIES:           # whitelist, not free text
        return {"error": "Unknown policy."}
    rows = query("SELECT policy_text FROM policies WHERE policy_key = %s", (policy_key,))
    return rows[0] if rows else {"error": "Policy not found."}


def escalate_to_human(reason):
    """No DB access: just signals a hand-off. The agent/API records it."""
    return {"status": "handoff_requested", "reason": str(reason)[:200]}


# ---------------------------------------------------------------- dispatch
def dispatch(name, args, customer_id):
    """
    Run one tool call requested by the LLM.

    `args` comes from the model (untrusted). `customer_id` comes from the API
    layer (trusted). They are combined here, and ONLY here.
    """
    args = args if isinstance(args, dict) else {}
    try:
        if name == "get_order_status":
            return get_order_status(args.get("order_id"), customer_id)
        if name == "get_refund_status":
            return get_refund_status(args.get("order_id"), customer_id)
        if name == "check_return_eligibility":
            return check_return_eligibility(args.get("order_id"), customer_id)
        if name == "list_recent_orders":
            return list_recent_orders(customer_id)
        if name == "get_policy":
            return get_policy(args.get("policy_key"))
        if name == "escalate_to_human":
            return escalate_to_human(args.get("reason", ""))
    except Exception:
        traceback.print_exc()                        # full error in the server log only
        return {"error": "Temporary problem fetching this information."}
    return {"error": f"Unknown tool: {name}"}
