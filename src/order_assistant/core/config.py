"""config.py - reads settings from environment variables (and a local .env file).

Nothing secret is ever written in code. Run commands from the project root so
the .env file is found.

Required : DB_HOST, DB_PORT, DB_NAME, DB_RO_USER, DB_RO_PASS
Optional : DB_AUDIT_*  (audit_writer user; without it only the JSONL log is written)
           DB_AUTH_*   (auth_reader user; needed for POST /login)
           JWT_SECRET_KEY (the API refuses to start without it)
           GROQ_API_KEY, GROQ_MODEL (read in agent/runner.py)
"""
import os

from dotenv import find_dotenv, load_dotenv

# usecwd=True: look for .env in the folder you run the command from,
# not next to this file (which would be deep inside src/).
load_dotenv(find_dotenv(usecwd=True))


def require(name):
    """Return an environment variable or fail loudly (never fail silently with None)."""
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def _db_settings(user_var, pass_var, required):
    """Build a connection dict for one MySQL user. Optional users return None."""
    if not required and os.getenv(user_var) is None:
        return None
    return {
        "host": require("DB_HOST"),
        "port": int(require("DB_PORT")),
        "user": require(user_var),
        "password": require(pass_var),
        "database": require("DB_NAME"),
    }


# Three separate MySQL users = least privilege. Each module uses only its own.
DB_RO = _db_settings("DB_RO_USER", "DB_RO_PASS", required=True)            # chatbot tools (SELECT only)
DB_AUDIT = _db_settings("DB_AUDIT_USER", "DB_AUDIT_PASS", required=False)  # INSERT on chat_audit_log
DB_AUTH = _db_settings("DB_AUTH_USER", "DB_AUTH_PASS", required=False)     # login only (3 columns)

# Secret used to sign JWTs. Anyone who knows it can forge a login token.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
