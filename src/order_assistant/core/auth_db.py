"""auth_db.py - the ONLY code allowed to read credentials.

It uses a different MySQL user (auth_reader) from the chatbot tools. That user
can read exactly three columns of `customers` (customer_id, email,
password_hash). Even if the chatbot side is ever compromised, it has no path
to password hashes, because it never touches this module's connection.
"""
import pymysql

from order_assistant.core.config import DB_AUTH


def get_login_record(email):
    """Return {"customer_id", "password_hash"} for this email, or None."""
    if DB_AUTH is None:
        raise RuntimeError("DB_AUTH_USER / DB_AUTH_PASS are not configured")
    conn = pymysql.connect(
        **DB_AUTH,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        read_timeout=5,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT customer_id, password_hash FROM customers WHERE email = %s",
                (email,),
            )
            return cur.fetchone()
    finally:
        conn.close()
