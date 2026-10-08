"""Shared test setup.

Real values from .env win; dummy values only fill gaps so unit tests also run
on a machine (or CI) that has no .env and no database.
"""
import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))
for key, value in {
    "DB_HOST": "127.0.0.1", "DB_PORT": "3306", "DB_NAME": "shop",
    "DB_RO_USER": "test", "DB_RO_PASS": "test",
    "JWT_SECRET_KEY": "unit-test-secret-key-0123456789-abcdefghij",
    "RATE_LIMIT_ENABLED": "false",          # tests make many calls from one "IP"
}.items():
    os.environ.setdefault(key, value)
