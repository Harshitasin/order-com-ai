"""audit.py - records every chat turn.

Two destinations:
  1. logs/chat_log.jsonl  - ALWAYS written. One JSON object per line. This file
     is your raw data for later analysis (error analysis, escalation rate,
     latency, tool-call accuracy) in a pandas notebook:
         pd.read_json("logs/chat_log.jsonl", lines=True)
  2. chat_audit_log table - written with the INSERT-only 'audit_writer' user,
     if DB_AUDIT exists in config.py. If it is missing or fails, we just skip
     it: logging must never break the chat.
"""
import json
import os
from datetime import datetime

import pymysql

from order_assistant.core.config import DB_AUDIT   # None if audit_writer is not configured

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "chat_log.jsonl")


def log_chat(customer_id, user_message, result, flagged, latency_ms):
    """
    Record one chat turn.

    result  : the dict returned by agent.runner.run_agent()
    flagged : True if guardrails.looks_suspicious() matched (stored as `blocked` in the DB;
              the request is still answered - the flag is for later analysis)
    """
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "customer_id": customer_id,
        "user_message": user_message,
        "reply": result["reply"],
        "tools_called": result["tools_called"],
        "escalated": result["escalated"],
        "rounds": result["rounds"],
        "flagged_suspicious": flagged,
        "latency_ms": latency_ms,
    }

    # 1) File log (always). "a" = append, so each turn adds one line.
    #    NOTE: logs/ is git-ignored because it contains real user messages.
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")

    # 2) DB log (best effort). Skipped silently when audit_writer is not configured.
    if DB_AUDIT is None:
        return
    try:
        # A short-lived connection per insert keeps this simple; use a pool if traffic grows.
        conn = pymysql.connect(
            host=DB_AUDIT["host"], port=DB_AUDIT["port"],
            user=DB_AUDIT["user"], password=DB_AUDIT["password"],
            database=DB_AUDIT["database"], connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chat_audit_log "
                    "(customer_id, user_message, tools_called, response_text, blocked) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (customer_id, user_message,
                     json.dumps(result["tools_called"], default=str),
                     result["reply"], flagged),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        # Never let a logging failure break the user's chat reply.
        print("audit DB insert failed (file log still written):", e)
