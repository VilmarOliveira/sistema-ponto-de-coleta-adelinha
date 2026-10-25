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


@pytest.mark.skipif(not os.environ.get('TEST_DATABASE_URL'), reason='TEST_DATABASE_URL não configurada')
def test_banner_and_pix_settings_persist_on_postgresql():
    import io
    from PIL import Image

    database_url = os.environ['TEST_DATABASE_URL']
    config = {'TESTING': True, 'SECRET_KEY': 'postgres-settings', 'DATABASE': database_url}
    app = create_app(config)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(staff='postgres-test', staff_legacy=True, csrf_token='pg-csrf')
    output = io.BytesIO()
    Image.new('RGB', (2048, 684), 'orange').save(output, 'PNG')
    image = output.getvalue()
    response = client.post('/painel/configuracoes/banners', data={
        'banner_id': '0', 'position': '1', 'alt_text': 'Banner PostgreSQL', 'active': 'yes',
        'image': (io.BytesIO(image), 'pg.png'), 'csrf_token': 'pg-csrf'})
    assert response.status_code == 302
    response = client.post('/painel/configuracoes/pix', data={
        'receiver': 'Titular PostgreSQL', 'pix_key_type': 'E-mail',
        'pix_key': 'postgres@example.com', 'csrf_token': 'pg-csrf'})
    assert response.status_code == 302
    restarted = create_app(config).test_client()
    assert restarted.get('/identidade/banner-principal').data == image
    assert 'Banner PostgreSQL' in restarted.get('/').text
    connection = DatabaseConnection(database_url)
    row = connection.execute('SELECT pix_key,pix_receiver_name FROM settings WHERE id=1').fetchone()
    assert row == {'pix_key': 'postgres@example.com', 'pix_receiver_name': 'Titular PostgreSQL'}
    connection.close()
