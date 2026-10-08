"""guardrails.py - small, simple guardrails around the LLM.

IMPORTANT: none of these are what actually protects customer data. That is
done by services/tools.py (SQL ownership check). These are extra layers, and
looks_suspicious() is a deliberately naive BASELINE: later you can replace it
with an ML classifier and compare the two on your adversarial eval set.
"""
import re

MAX_LEN = 500   # characters; also keeps token usage (and free-tier quota) small

# Naive patterns for prompt-injection / data-probing attempts, in English and Hinglish.
# It catches obvious attacks only; a determined attacker can rephrase around it.
_INJECTION_PATTERN = re.compile(
    r"(ignore (all |the )?(previous|above|prior)"
    r"|system prompt"
    r"|reveal .*(instruction|prompt|rules)"
    r"|other customers?"
    r"|all (the )?orders"
    r"|sab orders"          # Hinglish: "all orders"
    r"|customer_id"
    r"|you are now)",
    re.IGNORECASE,
)


def validate_input(message):
    """Return (ok, error_message). Rejects non-strings, blanks and over-long text."""
    if not isinstance(message, str) or not message.strip():
        return False, "Message is empty."
    if len(message) > MAX_LEN:
        return False, f"Message is too long (max {MAX_LEN} characters)."
    return True, None


def looks_suspicious(message):
    """Regex baseline for prompt-injection / data-probing attempts."""
    return bool(_INJECTION_PATTERN.search(message))


def mask_pii(text):
    """Hide emails and 10-digit phone numbers in the model's reply."""
    # 1) Any email address -> placeholder.
    text = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[email hidden]", text)
    # 2) Exactly 10 digits (a phone number): keep only the last 4.
    #    \b on both sides means longer numbers (tracking ids etc.) are left alone.
    text = re.sub(r"\b(\d{6})(\d{4})\b", r"XXXXXX\2", text)
    return text


def sanitize_history(history, keep_last=6):
    """
    The client sends past turns. They are untrusted: a user could fake an
    'assistant' message. So we keep only plain-text user/assistant turns.
    """
    clean = []
    for turn in (history or [])[-keep_last:]:          # only the most recent turns
        if (isinstance(turn, dict)
                and turn.get("role") in ("user", "assistant")   # drops "system"/"tool" roles
                and isinstance(turn.get("content"), str)):       # drops lists/objects
            clean.append({"role": turn["role"], "content": turn["content"][:MAX_LEN]})
    # The API requires the first message to be from the user.
    while clean and clean[0]["role"] != "user":
        clean.pop(0)
    return clean
