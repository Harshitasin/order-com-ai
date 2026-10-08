# Learning guide

Read the project in this order. For each file: read it once, run the "Try" step,
then answer the question in your own words before moving on.

| # | File | What to look for | Try |
|---|------|------------------|-----|
| 1 | `db/schema.sql` | Primary vs foreign key, ENUM, UNIQUE on `shipments.order_id` (one-to-one), why `order_items` is its own table (one-to-many), the composite index on `shipment_events` | Run `EXPLAIN SELECT * FROM orders WHERE customer_id = 1;` and read `key` and `rows` |
| 2 | `scripts/seed_data.py` | Edge cases are planted on purpose (late order, expired return window, non-returnable item). Dates are relative to "now" | Add one order with an `ADDRESS_ISSUE` event |
| 3 | `core/config.py` | Secrets come from the environment; `require()` fails loudly instead of returning `None` | Delete one variable from `.env` and read the error |
| 4 | `core/db.py` | connection -> cursor -> execute -> fetch; `try/finally` always closes the connection; `%s` placeholders; the SELECT-only guard | Call `query("DELETE FROM orders")` and read the error |
| 5 | `services/business_rules.py` | Pure functions: no database, easy to test. "Due today" is not late | Change `RETURN_WINDOW_DAYS` to 3 and see which unit tests fail |
| 6 | `services/tools.py` | **The security heart.** `_get_owned_order` filters on order id AND customer id. Missing and foreign orders return the identical `NOT_FOUND`. `dispatch` injects `customer_id` | Run `scripts/injection_demo.py`, then read `tests/integration/test_tools_db.py::test_zero_cross_customer_leakage` |
| 7 | `agent/tool_schemas.py`, `prompts.py`, `runner.py` | The model only *requests* a tool; our code runs it. No tool has a `customer_id` parameter. `MAX_TOOL_ROUNDS` stops loops | Print `messages` inside the loop to watch the conversation grow |
| 8 | `security/guardrails.py` | Input limits, a naive injection regex (a baseline, not protection), PII masking, untrusted chat history | Find an attack the regex misses |
| 9 | `core/auth_db.py`, `api/app.py` | JWT: signed, not encrypted. Identity only from the token. Same 401 for unknown email and wrong password. Dummy hash against timing leaks. Rate limits | Decode a token at jwt.io; change one character and call the API |
| 10 | `observability/audit.py` | JSONL log for analysis plus an INSERT-only DB user | Chat a few times, then `pd.read_json("logs/chat_log.jsonl", lines=True)` |
| 11 | `tests/` | Unit tests (no DB) vs integration tests (DB). Fakes via `monkeypatch`. The forged-token test | Break a rule on purpose and watch the right test fail |
| 12 | `eval/` | Synthetic labelled set, grouped cross-validation, baseline vs model, error analysis | Read `eval/results/intent_errors_tfidf_lr.csv` |

## Break it on purpose (the fastest way to understand security)

1. In `_get_owned_order`, remove `AND customer_id = %s`. Run the integration tests. Which fails, and why?
2. Give the read-only MySQL user `SELECT` on `customers`, then run the third case in `scripts/injection_demo.py`. Revoke it afterwards.
3. Add `customer_id` as a parameter of `get_order_status` in `tool_schemas.py` and let the model choose it. Ask the chatbot for another customer's order. This is the mistake the design avoids.
4. Set `JWT_ACCESS_TOKEN_EXPIRES` to 10 seconds and watch the UI log you out.
5. Replace `_DUMMY_HASH` with an early `return` for unknown emails and time both login paths.

## Questions you should be able to answer

1. Why is `customer_id` not a tool argument? Where does it come from instead?
2. Why do a missing order and someone else's order return the same response?
3. What does the SELECT-only guard protect against that parameterized queries do not?
4. A JWT payload is readable by anyone. Why can the user still not become customer 2?
5. Why does the chatbot's DB user have no access to `customers`?
6. Why are delays and return windows computed in Python and not by the LLM?
7. What does `finally` guarantee, and what breaks without it?
8. Why does the evaluation split by template, not by random rows?
9. A regex baseline can beat a trained model. When, and what does that say about the data?
10. What would you measure to decide whether this assistant is safe to launch?

## Interview summary (30 seconds)

"I built an LLM assistant for order tracking where data isolation does not depend on the model behaving. The model can only call tools; identity comes from a verified JWT and is injected server-side; every query filters by customer id in SQL; the database user is read-only and cannot read credentials. I tested it with a leakage sweep across every cross-customer order pair and evaluated intent routing against a baseline with grouped cross-validation."
