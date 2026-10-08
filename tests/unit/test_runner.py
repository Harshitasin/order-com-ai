"""Tests for the tool-calling loop in agent/runner.py.

The Groq client is replaced by a scripted fake, so no API key, network or
database is needed. We check the two things that matter most:
  1. customer_id is injected by OUR code, whatever arguments the model sends;
  2. failures (rate limit, endless tool loops, bad JSON) end safely.
"""
import json
from types import SimpleNamespace

import groq
import httpx
import pytest

from order_assistant.agent import runner
from order_assistant.agent.prompts import BUSY, FALLBACK


# ------------------------------------------------------------ fake helpers
def _tool_call(name, arguments, call_id="call_1"):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def _response(content=None, tool_calls=None):
    """Shape of client.chat.completions.create(...) result (only the fields we use)."""
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    """Returns scripted responses in order and records every request."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def use_fake(monkeypatch):
    """Install a FakeClient and a recording stand-in for dispatch()."""
    seen = []

    def install(script):
        fake = FakeClient(script)
        monkeypatch.setattr(runner, "_get_client", lambda: fake)
        return fake

    def fake_dispatch(name, args, customer_id):
        seen.append((name, args, customer_id))
        return {"error": "x"} if name == "boom" else {"ok": True}

    monkeypatch.setattr(runner, "dispatch", fake_dispatch)
    install.seen = seen
    return install


# ------------------------------------------------------------------- tests
def test_plain_answer_needs_no_tools(use_fake):
    fake = use_fake([_response(content="Hello!")])
    out = runner.run_agent(1, "hi")
    assert out["reply"] == "Hello!" and out["tools_called"] == [] and out["rounds"] == 1
    # The system prompt must be the first message, and the user's text the last.
    sent = fake.requests[0]["messages"]
    assert sent[0]["role"] == "system" and sent[-1] == {"role": "user", "content": "hi"}


def test_tool_call_then_answer_and_customer_id_is_injected(use_fake):
    # The model tries to smuggle in customer_id=2; dispatch must still get the trusted 1.
    args = json.dumps({"order_id": "ORD-100001", "customer_id": 2})
    fake = use_fake([
        _response(tool_calls=[_tool_call("get_order_status", args)]),
        _response(content="Your order is on its way."),
    ])
    out = runner.run_agent(1, "where is ORD-100001?")

    assert out["reply"] == "Your order is on its way." and out["rounds"] == 2
    name, _args, customer_id = use_fake.seen[0]
    assert name == "get_order_status" and customer_id == 1
    # The tool result was sent back as a "tool" message linked to the request.
    followup = fake.requests[1]["messages"]
    assert followup[-1]["role"] == "tool" and followup[-1]["tool_call_id"] == "call_1"
    assert json.loads(followup[-1]["content"]) == {"ok": True}


def test_escalation_is_reported(use_fake):
    use_fake([
        _response(tool_calls=[_tool_call("escalate_to_human", '{"reason": "angry"}')]),
        _response(content="A human agent will follow up."),
    ])
    assert runner.run_agent(1, "I want a manager")["escalated"] is True


@pytest.mark.parametrize("bad", ["", "not json", "[1, 2]", "null"])
def test_malformed_tool_arguments_become_empty_dict(use_fake, bad):
    use_fake([_response(tool_calls=[_tool_call("get_order_status", bad)]),
              _response(content="Please give me an order ID.")])
    runner.run_agent(1, "status?")
    assert use_fake.seen[0][1] == {}


def test_endless_tool_loop_stops_and_hands_off(use_fake):
    loop = [_response(tool_calls=[_tool_call("get_policy", '{"policy_key": "return_policy"}')])
            for _ in range(runner.MAX_TOOL_ROUNDS)]
    use_fake(loop)
    out = runner.run_agent(1, "loop forever")
    assert out["reply"] == FALLBACK and out["escalated"] is True
    assert out["rounds"] == runner.MAX_TOOL_ROUNDS


def _status_error(cls, code):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return cls("boom", response=httpx.Response(code, request=request), body=None)


def test_rate_limit_gives_busy_message_not_escalation(use_fake):
    use_fake([_status_error(groq.RateLimitError, 429)])
    out = runner.run_agent(1, "hi")
    assert out["reply"] == BUSY and out["escalated"] is False


def test_other_api_errors_fall_back_to_human(use_fake):
    use_fake([_status_error(groq.BadRequestError, 400)])
    out = runner.run_agent(1, "hi")
    assert out["reply"] == FALLBACK and out["escalated"] is True
