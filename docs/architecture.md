# Architecture notes

## Layers (dependencies point downward only)

```
api  ->  agent  ->  services  ->  core
 |                     ^
 +--> security         |
 +--> observability    |
```

- `api` knows HTTP and nothing about SQL.
- `agent` knows the LLM and the tool schemas, not SQL.
- `services` hold the rules and the queries; they are the only code that decides what data is returned.
- `core` is configuration and the database helper.

## Why business rules are plain Python

Dates and "is this order late?" are computed in code and passed to the LLM as facts.
This makes the answers testable (unit tests) and measurable (evaluation set).

## Identity

`POST /login` checks the password with the `auth_reader` DB user and returns a signed JWT
(1 hour). `current_customer_id()` in `api/app.py` reads the id from the verified token.
The URL, query string and request body are never used for identity.

## Logging

Every chat turn is appended to `logs/chat_log.jsonl` (raw data for analysis) and,
when configured, inserted into `chat_audit_log` by an INSERT-only DB user.
