"""Integration-test setup: skip everything unless a seeded MySQL is reachable."""
import pytest

from order_assistant.core.db import query


@pytest.fixture(scope="session", autouse=True)
def require_database():
    """Skip every integration test when MySQL is unreachable or not seeded."""
    try:
        query("SELECT 1 FROM orders LIMIT 1")
    except Exception as e:
        pytest.skip(f"database not available: {e}", allow_module_level=False)
