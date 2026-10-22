"""Smoke test opcional para PostgreSQL/Neon.

Defina TEST_DATABASE_URL somente em CI ou em um projeto Neon de teste. O teste
cria apenas estruturas ausentes e nunca remove tabelas ou registros.
"""
import os

import pytest

pytest.importorskip("flask")
pytest.importorskip("psycopg")

from app import CLIENT_COLUMNS, DatabaseConnection, create_app


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL não configurada")
def test_neon_schema_and_queries_are_postgresql_compatible():
    database_url = os.environ["TEST_DATABASE_URL"]
    app = create_app({"TESTING": True, "SECRET_KEY": "postgres-test", "DATABASE": database_url})
    client = app.test_client()
    assert client.get("/health").json == {"status": "ok"}

    connection = DatabaseConnection(database_url)
    assert connection.postgres
    columns = connection.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='clients'"
    ).fetchall()
    assert set(CLIENT_COLUMNS.split(",")) <= {row["column_name"] for row in columns}
    connection.close()
