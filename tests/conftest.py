import os

import psycopg
import pytest


def connect(user: str, password_variable: str) -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=user,
        password=os.environ[password_variable],
    )


@pytest.fixture
def writer():
    """A vessel_writer connection. Each test's changes are rolled back."""
    with connect("vessel_writer", "VESSEL_WRITER_PASSWORD") as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def reader():
    """A vessel_reader connection. Each test's changes are rolled back."""
    with connect("vessel_reader", "VESSEL_READER_PASSWORD") as conn:
        yield conn
        conn.rollback()
