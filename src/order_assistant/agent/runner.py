"""runner.py - the LLM tool-calling loop (powered by Groq).

Flow for one user message:
  1. Send system prompt + conversation + tool definitions to the model.
  2. If the model asks for tool(s) -> run each one via services.tools.dispatch()
     (customer_id injected by US, never by the model), send the results back,
     and ask the model again.
  3. When the model answers in plain text -> return it.

Setup (see .env.example):
  GROQ_API_KEY  required. Free key from https://console.groq.com/keys
  GROQ_MODEL    optional. Any Groq-hosted model that supports tool use.
                Groq changes its model list from time to time, so check
                https://console.groq.com/docs/models if the default stops working.

Free-tier note: Groq's free tier is limited by requests/minute and tokens/minute,
not by money. When the limit is hit we return a friendly "busy" message
instead of crashing.
"""
import json
import os
import traceback

import groq
from dotenv import find_dotenv, load_dotenv

from order_assistant.agent.prompts import BUSY, FALLBACK, SYSTEM
from order_assistant.agent.tool_schemas import TOOLS
from order_assistant.services.tools import dispatch

# Load .env from the directory the command is run in (the project root).
load_dotenv(find_dotenv(usecwd=True))

# Default is a Groq-hosted Llama model that supports tool calling. Override in .env.
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_TOOL_ROUNDS = 4          # hard stop so a confused model cannot loop forever
MAX_TOKENS = 700             # caps reply length (and token usage on the free tier)
TEMPERATURE = 0              # 0 = most deterministic; we want consistent tool choices

_client = None


def _get_client():
    """Create the API client on first use (keeps imports and unit tests key-free)."""
    global _client
    if _client is None:
        # Reads GROQ_API_KEY from the environment automatically.
        _client = groq.Groq()
    return _client


def _parse_arguments(raw):
    """
    The model returns tool arguments as a JSON *string*. It is untrusted text:
    it can be empty, malformed, or not an object. Anything unusable becomes {}
    and the tool layer then answers with a safe error.
    """
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return args if isinstance(args, dict) else {}


def run_agent(customer_id, message, history=None):
    """
    Returns a dict (easy to log and to evaluate later):
      reply        : final text for the user
      tools_called : [{"tool", "args", "result_is_error"}, ...]
      escalated    : True if the model requested a human hand-off
      rounds       : number of model calls used

    customer_id is trusted (it comes from the verified JWT in the API layer).
    message and history are untrusted user input.
    """
    # The system prompt is the first message in OpenAI-compatible APIs.
    messages = [{"role": "system", "content": SYSTEM}]
    messages += list(history or [])
    messages.append({"role": "user", "content": message})
    tools_called, escalated = [], False

    for round_no in range(1, MAX_TOOL_ROUNDS + 1):
        try:
            resp = _get_client().chat.completions.create(
                model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto",
                max_tokens=MAX_TOKENS, temperature=TEMPERATURE,
            )
        except groq.RateLimitError:
            # Free-tier limit reached. Not the user's fault and not a hand-off case.
            traceback.print_exc()
            return {"reply": BUSY, "tools_called": tools_called,
                    "escalated": False, "rounds": round_no}
        except groq.APIError:
            # Covers connection errors, bad requests (the model sometimes emits a
            # malformed tool call) and server errors. Fail safe: hand off to a human.
            traceback.print_exc()
            return {"reply": FALLBACK, "tools_called": tools_called,
                    "escalated": True, "rounds": round_no}

        msg = resp.choices[0].message

        # No tool requested -> this is the final answer.
        if not msg.tool_calls:
            return {"reply": msg.content or "", "tools_called": tools_called,
                    "escalated": escalated, "rounds": round_no}

        # Keep the model's turn in the conversation. We rebuild it as a plain dict
        # so only the fields the API expects are sent back.
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })

        # Run every requested tool and answer each one with a "tool" message.
        for tc in msg.tool_calls:
            args = _parse_arguments(tc.function.arguments)
            output = dispatch(tc.function.name, args, customer_id)   # <- trusted id injected here
            if tc.function.name == "escalate_to_human":
                escalated = True
            tools_called.append({"tool": tc.function.name, "args": args,
                                 "result_is_error": "error" in output})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,                       # links the result to the request
                "content": json.dumps(output, default=str),  # default=str handles dates / Decimal
            })

    # The model kept asking for tools: give up safely and hand off to a human.
    return {"reply": FALLBACK, "tools_called": tools_called,
            "escalated": True, "rounds": MAX_TOOL_ROUNDS}
