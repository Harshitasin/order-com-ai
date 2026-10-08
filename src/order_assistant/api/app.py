"""api/app.py - Flask API with JWT login, ownership enforcement and rate limits.

Endpoints
  GET  /                 chat UI (static page)
  GET  /health           liveness check (used by Docker / hosting platforms)
  POST /login            {"email", "password"} -> {"access_token"}
  GET  /order/<order_id> (needs token)
  POST /chat             {"message", "history"?} (needs token)

THE CORE SECURITY RULE
  The customer id comes ONLY from the verified token (current_customer_id()).
  It is never read from the URL, query string or request body, so a user
  cannot ask for "customer 2" by editing a request.
"""
import os
import time
from datetime import timedelta

from flask import Flask, jsonify, request
from flask_jwt_extended import (
    JWTManager, create_access_token, get_jwt_identity, jwt_required,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

from order_assistant.agent.runner import run_agent
from order_assistant.core.auth_db import get_login_record
from order_assistant.core.config import JWT_SECRET_KEY
from order_assistant.observability.audit import log_chat
from order_assistant.security.guardrails import (
    looks_suspicious, mask_pii, sanitize_history, validate_input,
)
from order_assistant.services.tools import NOT_FOUND, get_order_status

# Fail at startup, not at the first login: a missing secret is a deployment bug.
if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is not set (see .env.example)")

app = Flask(__name__)                       # serves ./static automatically
app.config["JWT_SECRET_KEY"] = JWT_SECRET_KEY
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)    # limits damage if a token leaks
# Tests turn the limiter off (RATE_LIMIT_ENABLED=false) because they call from one "IP" in a loop.
app.config["RATELIMIT_ENABLED"] = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"

jwt = JWTManager(app)

# Rate limiting is per client IP. "memory://" keeps counters inside the process:
# fine for one server; use Redis if you run several workers/instances and need shared counters.
limiter = Limiter(get_remote_address, app=app,
                  default_limits=["120/minute"], storage_uri="memory://")


# ------------------------------------------------------------ auth errors
# One consistent 401 for every authentication problem (the UI handles just one case).
@jwt.unauthorized_loader
def _no_token(reason):
    return jsonify(error="Authentication required"), 401


@jwt.invalid_token_loader
def _bad_token(reason):
    return jsonify(error="Invalid token"), 401


@jwt.expired_token_loader
def _expired(header, payload):
    return jsonify(error="Token expired"), 401


def current_customer_id():
    """Customer id from the verified JWT. The ONLY source of identity."""
    return int(get_jwt_identity())


# A real hash to compare against when the email does not exist, so a wrong email
# takes about as long as a wrong password (no timing hint about which emails exist).
_DUMMY_HASH = generate_password_hash("not-a-real-password")


# ------------------------------------------------------------------ routes
@app.get("/")
def index():
    """Serve the single-page chat UI from api/static/index.html."""
    return app.send_static_file("index.html")


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/login")
@limiter.limit("10/minute")                 # slows down password guessing
def login():
    # silent=True -> a bad/missing JSON body gives None instead of raising; we treat it as {}.
    data = request.get_json(silent=True) or {}
    email, password = data.get("email"), data.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify(error="email and password are required"), 400

    record = get_login_record(email)
    # Always run one hash comparison (real or dummy) so timing does not reveal valid emails.
    password_ok = check_password_hash(record["password_hash"] if record else _DUMMY_HASH, password)

    # Same status and same message for "no such email" and "wrong password".
    if record is None or not password_ok:
        return jsonify(error="Invalid email or password"), 401

    # The token's "sub" claim carries the customer id; it is signed, so it cannot be edited.
    return jsonify(access_token=create_access_token(identity=str(record["customer_id"])))


@app.get("/order/<order_id>")
@jwt_required()
def order(order_id):
    """Direct order lookup (no LLM). Handy for debugging and for the ownership tests."""
    result = get_order_status(order_id, current_customer_id())
    if result == NOT_FOUND:
        # Same status and body whether the order is missing or belongs to someone else.
        return jsonify(NOT_FOUND), 404
    return jsonify(result)


@app.post("/chat")
@limiter.limit("20/minute")                 # every call uses LLM quota: keep this low
@jwt_required()
def chat():
    customer_id = current_customer_id()     # trusted: comes from the verified token
    body = request.get_json(silent=True) or {}

    # 1) Validate the (untrusted) message.
    message = body.get("message", "")
    ok, err = validate_input(message)
    if not ok:
        return jsonify(error=err), 400

    # 2) Flag + log suspicious wording. We do NOT block on it: the real protection
    #    is the SQL ownership check in services/tools.py. The flag is for analysis.
    flagged = looks_suspicious(message)
    history = sanitize_history(body.get("history"))

    # 3) Ask the LLM agent (it may call tools; customer_id is injected inside).
    start = time.perf_counter()
    result = run_agent(customer_id, message, history)
    latency_ms = int((time.perf_counter() - start) * 1000)

    # 4) Last line of defence: hide emails / phone numbers, then log the turn.
    result["reply"] = mask_pii(result["reply"])
    log_chat(customer_id, message, result, flagged, latency_ms)
    return jsonify(reply=result["reply"], escalated=result["escalated"])


# Must stay at the very bottom: routes above have to be registered first.
# This block only runs for `python -m order_assistant.api.app` (local development).
# In Docker, gunicorn imports `app` directly and never reaches this line.
if __name__ == "__main__":
    # Debug mode lets anyone who can reach the server run code, so it is OFF by default.
    # Turn it on only on your own machine: set FLASK_DEBUG=true in .env.
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
