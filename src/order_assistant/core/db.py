"""db.py - the ONLY place in the project that talks to MySQL for reads.

Rules this file enforces:
  1. It connects with the read-only user (DB_RO from config.py), never root.
  2. Every query goes through query(sql, params), so values are always
     passed as parameters (%s) and never glued into the SQL string.
  3. Only SELECT statements are allowed (extra safety on top of DB permissions).
  4. The connection is always closed, even if the query fails.
"""
import pymysql

from order_assistant.core.config import DB_RO


def _get_connection():
    """Open a new connection using the read-only credentials."""
    return pymysql.connect(
        host=DB_RO["host"],
        port=DB_RO["port"],
        user=DB_RO["user"],
        password=DB_RO["password"],
        database=DB_RO["database"],
        cursorclass=pymysql.cursors.DictCursor,  # rows come back as dicts: row["order_id"]
        connect_timeout=5,                       # give up if DB is unreachable
        read_timeout=5,                          # give up if a query hangs
    )


def query(sql, params=()):
    """
    Run a read-only SQL query and return a list of dict rows.

    Example:
        query("SELECT * FROM orders WHERE customer_id = %s", (1,))

    Always pass values in `params`. NEVER build `sql` with f-strings.
    """
    # Layer 3 of defence: refuse anything that is not a SELECT.
    # (Layer 1 = parameterized queries, Layer 2 = DB user permissions.)
    if not sql.lstrip().upper().startswith("SELECT"):
        raise ValueError("db.query() only allows SELECT statements")

    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)   # pymysql safely escapes params here
            return cur.fetchall()      # list of dicts ([] if nothing matched)
    finally:
        conn.close()                   # runs even if execute() raised an error
