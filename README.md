# Order & Shipment Tracking Assistant

![CI](https://github.com/<Harshitasin>/order-assistant/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

An LLM-powered customer-support assistant that answers order status, delay,
refund and return questions from a MySQL database, built so that **one customer
can never see another customer's data**. It runs on the **Groq API (free tier)**
with a Llama model, so you can try it without paying for an LLM.

## How it works

```
browser UI -> POST /chat (JWT) -> agent (LLM tool calling) -> services/tools (SQL, ownership enforced)
                                                            -> services/business_rules (delay, returns)
           <- masked reply, audit log <-
```

The model never touches the database. It can only *ask* for one of six tools;
our code runs the tool and injects the customer id from the login token.

## Security model

1. `customer_id` comes only from the verified JWT. It is never read from the request and the LLM cannot choose it.
2. Every order query filters on `order_id` **and** `customer_id` in SQL.
3. "Order does not exist" and "order belongs to someone else" return the same response.
4. The chatbot's MySQL user is read-only and cannot read `customers`; login uses a separate user limited to three columns.
5. Queries are parameterized, order IDs are format-checked, and `db.query()` only allows SELECT.
6. Rate limits on `/login` and `/chat`; tokens expire after one hour.

## Tech stack

Python 3.10+, Flask, flask-jwt-extended, flask-limiter, MySQL 8 (PyMySQL), Groq API, Docker, pytest, GitHub Actions.

## Quick start (local)

Prerequisites: Python 3.10+, MySQL 8, and a free Groq API key from <https://console.groq.com/keys> (no credit card needed).

```bash
python -m venv .venv
.venv\Scripts\activate                      # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                        # fill it in (see comments inside), incl. GROQ_API_KEY
mysql -u root -p < db/schema.sql            # fresh database only
mysql -u root -p < db/grants.sql            # after replacing the <PLACEHOLDERS>
python scripts/seed_data.py
pytest -v
python -m order_assistant.api.app           # open http://127.0.0.1:5000
```

Demo logins (fake seed data only): `test1@example.com` and `test2@example.com`, password `Test@1234`.
Try: *"Where is ORD-100003?"*, *"Can I return ORD-100002?"*, *"mera refund kab aayega ORD-100005?"*

With Docker: see [docs/DEPLOY.md](docs/DEPLOY.md).

## Configuration

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Your Groq key (required for `/chat`) |
| `GROQ_MODEL` | Groq model to use; must support tool calling. Default `llama-3.3-70b-versatile`. Groq updates its model list now and then, see [console.groq.com/docs/models](https://console.groq.com/docs/models) |
| `JWT_SECRET_KEY` | Signs login tokens (the app will not start without it) |
| `DB_*` | Three MySQL users with different privileges, see `.env.example` |
| `FLASK_DEBUG` | `true` only on your own machine |

## Groq free tier: what to expect

The free tier is limited by requests and tokens per minute (not by money), and the limits depend on the model and can change; check [console.groq.com/settings/limits](https://console.groq.com/settings/limits). When the limit is hit, the assistant replies "please try again in a minute" instead of failing. The `/chat` endpoint is also limited to 20 requests per minute per IP to protect your quota.

## Project layout

```
src/order_assistant/
  core/            config, db (read-only helper), auth_db (login-only helper)
  services/        tools (what the LLM may call), business_rules (delay, returns)
  agent/           runner (Groq tool-calling loop), prompts, tool_schemas
  routing/         rules (keyword intent baseline, used by eval/)
  security/        guardrails (validation, injection flag, PII masking)
  observability/   audit (JSONL + DB logging)
  api/             Flask app + static chat UI
db/                schema.sql, grants.sql
scripts/           seed_data.py, injection_demo.py
tests/             unit/ (no DB or API key needed), integration/ (needs seeded MySQL)
eval/              eval set builder, intent comparison, agent evaluation, results
docs/              architecture, learning guide, deployment
```

## Tests

```bash
pytest -v        # unit tests always run; integration tests skip themselves without MySQL
```

The unit tests replace the Groq client and the database with fakes, so they need no key and no network.

## Evaluation

`eval/` compares intent-routing methods and measures tool accuracy and
cross-customer leakage. See [eval/README.md](eval/README.md) for results and their limits.

## Limitations

- Demo project with fake data; not audited for production use.
- The injection filter is a naive regex baseline. Real protection comes from the SQL ownership check, not from the filter or the prompt.
- Rate-limit counters live in process memory (use Redis for several servers).
- The evaluation set is synthetic; see the eval README before quoting numbers.

## Learn from this repo

[docs/LEARNING_GUIDE.md](docs/LEARNING_GUIDE.md) gives a reading order, experiments and self-check questions.

## License

MIT, see [LICENSE](LICENSE).
