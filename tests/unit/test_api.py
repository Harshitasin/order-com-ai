"""Basic API behaviour that needs neither the database nor the LLM."""
import pytest

from order_assistant.api import app as app_module


@pytest.fixture
def client():
    return app_module.app.test_client()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.get_json() == {"status": "ok"}


def test_chat_ui_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and b"Order" in r.data


def test_protected_routes_need_a_token(client):
    assert client.get("/order/ORD-100001").status_code == 401
    assert client.post("/chat", json={"message": "hi"}).status_code == 401


def test_login_validates_input_shape(client):
    assert client.post("/login", json={}).status_code == 400
    assert client.post("/login", json={"email": 1, "password": 2}).status_code == 400
