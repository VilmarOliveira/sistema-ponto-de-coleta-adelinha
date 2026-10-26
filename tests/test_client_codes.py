import hashlib
import re
import sqlite3

import app as app_module
from app import create_app, next_public_code
from test_app import register, signature
from test_customization import csrf, legacy_login


def test_migrates_client_code_preserving_contract_and_receipt(tmp_path, monkeypatch):
    database = str(tmp_path / 'codes.db')
    config = {'TESTING': True, 'SECRET_KEY': 'test', 'DATABASE': database}
    app = create_app(config)
    client = app.test_client()
    legacy_login(client)
    # Emite o cadastro com o código anterior, incluindo o hash original do aceite.
    with monkeypatch.context() as patch:
        patch.setattr(app_module, 'next_public_code', lambda connection, prefix: next_public_code(connection, 'CLTPCA' if prefix == 'CLIPCA' else prefix))
        assert 'CLTPCA-1' in register(client).text
    client.post('/pacotes', data={'client_id': 1, 'tracking': 'LEGADO', 'shelf': 'A1',
        'width': 10, 'height': 10, 'length': 10, 'weight': 1, 'csrf_token': csrf(client)})
    client.post('/pacotes/1/avisar', data={'csrf_token': csrf(client)})
    client.post('/retiradas', data={'package_ids': '1', 'receiver_name': 'Cliente Teste',
        'receiver_document': '52998224725', 'document_type': 'CPF', 'payment_method': 'Dinheiro',
        'payment_confirmed': 'yes', 'pickup_signature': signature(), 'csrf_token': csrf(client)})
    receipt_before = client.get('/comprovantes/1/pacotes/1.pdf').data
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        original = dict(connection.execute('SELECT * FROM clients').fetchone())
        historical = [tuple(row) for row in connection.execute('SELECT * FROM pickup_packages')]
        # Simula uma base anterior à existência das duas colunas históricas.
        connection.execute('ALTER TABLE clients DROP COLUMN legacy_public_id')
        connection.execute('ALTER TABLE clients DROP COLUMN contract_public_id')
    for _ in range(2):
        restored = create_app(config).test_client()
        legacy_login(restored)
        for query in ('CLIPCA-1', 'cltpca-1'):
            result = restored.get('/painel/clientes/busca', query_string={'q': query})
            assert result.json['clients'][0]['public_id'] == 'CLIPCA-1'
            assert 'Cliente Teste' in restored.get('/painel/configuracoes/usuarios', query_string={'q_clients': query}).text
        with sqlite3.connect(database) as connection:
            connection.row_factory = sqlite3.Row
            current = dict(connection.execute('SELECT * FROM clients').fetchone())
            assert current['id'] == original['id']
            assert current['public_id'] == 'CLIPCA-1'
            assert current['legacy_public_id'] == current['contract_public_id'] == 'CLTPCA-1'
            assert current['contract_hash'] == original['contract_hash']
            assert hashlib.sha256(''.join(current[key] for key in ('contract_public_id', 'name', 'cpf', 'terms_text', 'signature', 'accepted_at')).encode()).hexdigest() == current['contract_hash']
            assert [tuple(row) for row in connection.execute('SELECT * FROM pickup_packages')] == historical
            assert connection.execute('SELECT client_id FROM packages').fetchone()[0] == 1
        receipt_after = restored.get('/comprovantes/1/pacotes/1.pdf').data
        assert re.findall(rb'stream(.*?)endstream', receipt_after, re.S) == re.findall(rb'stream(.*?)endstream', receipt_before, re.S)
        with restored.session_transaction() as session:
            session['client_id'] = 1
            session['client_session_version'] = 1
        assert 'CLTPCA-1' in restored.get('/cliente/condicoes-aceitas').text
        assert restored.get('/cliente/contrato-assinado.pdf').status_code == 200
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT last_value FROM id_sequences WHERE prefix='CLIPCA'").fetchone()[0] == 1


def test_sequence_reserves_old_numbers_and_handles_collisions(tmp_path):
    database = str(tmp_path / 'mixed.db')
    config = {'TESTING': True, 'SECRET_KEY': 'test', 'DATABASE': database}
    create_app(config)
    with sqlite3.connect(database) as connection:
        for index, code in enumerate(('CLTPCA-1', 'CLIPCA-1', 'CLTPCA-7', 'ADL-000099'), start=1):
            connection.execute('INSERT INTO clients(id,public_id,name,cpf,phone,terms_version,signature,accepted_at) VALUES(?,?,?,?,?,?,?,?)',
                               (index, code, 'Cliente ' + str(index), str(index), '16999999999', 'v1', signature(), '2026-01-01'))
        # Inclui números já emitidos, mesmo que os cadastros tenham sido excluídos.
        connection.execute("INSERT INTO id_sequences(prefix,last_value) VALUES('CLTPCA',42)")
    migrated = create_app(config).test_client()
    legacy_login(migrated)
    result = migrated.get("/painel/clientes/busca", query_string={"q": "CLTPCA-1"})
    assert [(row["id"], row["public_id"]) for row in result.json["clients"]] == [(1, "CLIPCA-43")]
    listing = migrated.get("/painel/configuracoes/usuarios", query_string={"q_clients": "CLTPCA-1"}).text
    assert "CLIPCA-43" in listing and "CLIPCA-7" not in listing
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT public_id FROM clients ORDER BY id').fetchall() == [('CLIPCA-43',), ('CLIPCA-1',), ('CLIPCA-7',), ('ADL-000099',)]
    connection = app_module.DatabaseConnection(database)
    assert next_public_code(connection, 'CLIPCA') == 'CLIPCA-44'
    connection.commit()
    connection.close()
    create_app(config)
    connection = app_module.DatabaseConnection(database)
    assert next_public_code(connection, 'CLIPCA') == 'CLIPCA-45'
    connection.close()
