"""injection_demo.py - why we use parameterized queries AND a least-privilege DB user.

Run from the project root:  python scripts/injection_demo.py
unsafe() builds SQL with an f-string (BAD). safe() uses a %s placeholder (GOOD).
"""
import pymysql

from order_assistant.core.config import DB_RO


def _conn():
    return pymysql.connect(**DB_RO, cursorclass=pymysql.cursors.DictCursor)


def unsafe(order_id):
    sql = f"SELECT * FROM orders WHERE order_id = '{order_id}'"      # BAD: input becomes SQL
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def safe(order_id):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))   # GOOD
            return cur.fetchall()
    finally:
        conn.close()


TESTS = [
    "ORD-100001",
    "x' OR '1'='1",
    "x' UNION SELECT customer_id, name, email, 1, 1, 1 FROM customers -- ",
]

if __name__ == "__main__":
    for t in TESTS:
        print("\nINPUT:", t)
        for fn in (unsafe, safe):
            try:
                print(f"  {fn.__name__:7} -> {len(fn(t))} rows")
            except Exception as e:
                print(f"  {fn.__name__:7} -> ERROR: {e}")
