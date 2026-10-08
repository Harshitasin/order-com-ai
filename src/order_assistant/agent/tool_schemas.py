"""tool_schemas.py - the tools the LLM may call (names, descriptions, JSON schemas).

The real implementations live in services/tools.py. This file only *describes*
them to the model, so the model knows what it is allowed to ask for.

Format: Groq uses the OpenAI-compatible "function calling" shape:
    {"type": "function", "function": {"name", "description", "parameters": <JSON Schema>}}

SECURITY NOTE: no tool has a `customer_id` parameter. That is deliberate. The
model must never choose whose data to read; the server injects the id from the
verified JWT (see services/tools.py -> dispatch()).
"""


def _tool(name, description, properties=None, required=()):
    """Small helper that wraps a JSON Schema in the function-calling envelope."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": list(required),
            },
        },
    }


# Shared parameter: most tools work on a single order.
_ORDER_ID = {"order_id": {"type": "string", "description": "Order ID such as ORD-100001"}}

TOOLS = [
    _tool("get_order_status",
          "Get status, items, shipment tracking and delay info for one order.",
          _ORDER_ID, required=["order_id"]),

    _tool("get_refund_status",
          "Get refund status for one order.",
          _ORDER_ID, required=["order_id"]),

    _tool("check_return_eligibility",
          "Check whether an order can still be returned and until when.",
          _ORDER_ID, required=["order_id"]),

    # No parameters at all: "whose orders?" is answered by the JWT, not by the model.
    _tool("list_recent_orders",
          "List the logged-in customer's most recent orders."),

    # `enum` restricts the model to a whitelist (tools.py checks it again server-side).
    _tool("get_policy",
          "Get the store policy text.",
          {"policy_key": {"type": "string",
                          "enum": ["return_policy", "refund_timeline", "cancellation_policy"]}},
          required=["policy_key"]),

    _tool("escalate_to_human",
          "Hand the conversation to a human agent (refund approval, complaint, compensation, out-of-scope).",
          {"reason": {"type": "string"}},
          required=["reason"]),
]
