"""Authentication and identity tests. The DB, LLM and logger are replaced with fakes."""
import base64
import json
from datetime import timedelta

import pytest
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from order_assistant.api import app as app_module
from order_assistant.services.tools import NOT_FOUND

USERS = {"a@x.com": {"customer_id": 1, "password_hash": generate_password_hash("pw12345")}}


@pytest.fixture
def client():
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def fake_login_db(monkeypatch):
    monkeypatch.setattr(app_module, "get_login_record", lambda email: USERS.get(email))


def login(client, email="a@x.com", password="pw12345"):
    return client.post("/login", json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_success_returns_token(client):
    r = login(client)
    assert r.status_code == 200 and r.get_json()["access_token"]


def test_wrong_password_and_unknown_email_look_identical(client):
    wrong_pw = login(client, password="nope")
    no_user = login(client, email="ghost@x.com")
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.get_json() == no_user.get_json()


def test_garbage_token_is_rejected(client):
    assert client.get("/order/ORD-100001", headers=bearer("not.a.token")).status_code == 401


def test_forged_token_is_rejected(client):
    """Change the customer id inside the token but keep the old signature."""
    token = login(client).get_json()["access_token"]
    header, payload, signature = token.split(".")
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    data["sub"] = "2"
    forged_payload = base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    forged = ".".join([header, forged_payload, signature])
    assert client.get("/order/ORD-100200", headers=bearer(forged)).status_code == 401


def test_expired_token_is_rejected(client):
    with app_module.app.app_context():
        expired = create_access_token(identity="1", expires_delta=timedelta(seconds=-1))
    assert client.get("/order/ORD-100001", headers=bearer(expired)).status_code == 401


def test_order_identity_comes_from_token_not_from_request(client, monkeypatch):
    seen = {}

    def fake_get_order_status(order_id, customer_id):
        seen["customer_id"] = customer_id
        return NOT_FOUND

    monkeypatch.setattr(app_module, "get_order_status", fake_get_order_status)
    token = login(client).get_json()["access_token"]

    # The caller tries to claim customer 2 in the query string. It must be ignored.
    r = client.get("/order/ORD-100200?customer_id=2", headers=bearer(token))
    assert seen["customer_id"] == 1
    assert r.status_code == 404 and r.get_json() == NOT_FOUND


def test_chat_identity_comes_from_token_not_from_body(client, monkeypatch):
    seen = {}

    def fake_run_agent(customer_id, message, history):
        seen["customer_id"] = customer_id
        return {"reply": "ok", "tools_called": [], "escalated": False, "rounds": 1}

    monkeypatch.setattr(app_module, "run_agent", fake_run_agent)
    monkeypatch.setattr(app_module, "log_chat", lambda *a, **k: None)
    token = login(client).get_json()["access_token"]

    r = client.post("/chat", json={"message": "hello", "customer_id": 2}, headers=bearer(token))
    assert r.status_code == 200 and seen["customer_id"] == 1


def test_chat_rejects_empty_and_oversized_messages(client):
    token = login(client).get_json()["access_token"]
    assert client.post("/chat", json={"message": ""}, headers=bearer(token)).status_code == 400
    assert client.post("/chat", json={"message": "x" * 501}, headers=bearer(token)).status_code == 400
