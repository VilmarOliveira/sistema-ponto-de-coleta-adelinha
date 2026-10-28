import io
import sqlite3

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from app import create_app, IMAGE_UPLOAD_MAX_BYTES
from test_customization import csrf, legacy_login

PATH = '/painel/configuracoes/cartoes-explicativos'


def picture(format='PNG', size=(800, 1200)):
    output = io.BytesIO()
    Image.new('RGB', size, 'orange').save(output, format)
    return output.getvalue()


@pytest.fixture
def site(tmp_path):
    config = {'TESTING': True, 'SECRET_KEY': 'test', 'DATABASE': str(tmp_path / 'cards.db')}
    app = create_app(config)
    client = app.test_client()
    legacy_login(client)
    return app, client, config


def save(client, content=None, **fields):
    data = {'card_id': '1', 'title': 'Meu cadastro', 'alt_text': 'Como se cadastrar', 'csrf_token': csrf(client), **fields}
    if content is not None:
        data['image'] = (io.BytesIO(content), 'upload.jpg')
    return client.post(PATH, data=data, follow_redirects=True)


def test_initial_content_and_lazy_markup(site):
    app, client, config = site
    page = client.get('/').text
    for title in ('Cadastre-se', 'Use nosso endereço', 'Identifique seu pacote', 'Aguarde e retire'):
        assert title in page
    assert page.count('data-card-enlarge') == 4
    assert 'variant=' not in page
    assert '/1/celular?v=initial-v1' in page
    assert 'loading="lazy"' in page
    for variant in ('celular', 'computador', 'original'):
        response = client.get(f'/cartoes-explicativos/1/{variant}?v=initial-v1')
        assert response.status_code == 200 and response.mimetype == 'image/svg+xml'
    assert '800 × 1200 px' in client.get(PATH).text


@pytest.mark.parametrize('format,size', [('PNG',(800,1200)), ('JPEG',(1200,500)), ('WEBP',(300,700))])
def test_upload_real_format_derivatives_and_restart(site, format, size):
    app, client, config = site
    content = picture(format, size)
    response = save(client, content)
    assert response.status_code == 200 and 'Cartão atualizado com sucesso!' in response.text
    with sqlite3.connect(config['DATABASE']) as db:
        row = db.execute('SELECT image,thumbnail_small,thumbnail_large,revision,width,height FROM explanatory_cards WHERE id=1').fetchone()
    assert row[0] == content and tuple(row[4:]) == size
    for thumb, bounds in zip(row[1:3], ((320,480),(640,960))):
        with Image.open(io.BytesIO(thumb)) as image:
            assert image.format == 'WEBP'
            assert image.width <= bounds[0] and image.height <= bounds[1]
            assert abs(image.width/image.height - size[0]/size[1]) < .01
    restarted = create_app(config).test_client()
    assert 'Meu cadastro' in restarted.get('/').text
    uri = f'/cartoes-explicativos/1/original?v={row[3]}'
    image = restarted.get(uri)
    assert image.data == content and 'immutable' in image.headers['Cache-Control']
    assert 'public' in client.get(uri).headers['Cache-Control']
    assert restarted.get(uri, headers={'If-None-Match':image.headers['ETag']}).status_code == 304
    assert restarted.get('/cartoes-explicativos/1/original?v=initial-v1').status_code == 302
    assert restarted.get('/cartoes-explicativos/1/invalid').status_code == 404


def test_failed_upload_atomic_preservation_cancel_and_limit(site):
    app, client, config = site
    content = picture()
    exact_limit = content + b'\0' * (IMAGE_UPLOAD_MAX_BYTES - len(content))
    assert save(client, exact_limit).status_code == 200
    def rows():
        with sqlite3.connect(config['DATABASE']) as db:
            return db.execute('SELECT * FROM explanatory_cards ORDER BY id').fetchall()
    before = rows()
    for bad in (exact_limit + b'0', b'GIF89a', b'\x89PNG\r\n\x1a\ninvalid', b''):
        result = save(client, bad, title='Não salvar')
        assert result.status_code == 400 and 'imagem anterior foi preservada' in result.text
        assert rows() == before
    assert save(client, title='').status_code == 400 and rows() == before
    assert client.get(PATH).status_code == 200 and rows() == before  # Cancel is a GET.
    assert save(client, title='Título sem substituir').status_code == 200
    after = rows()
    assert after[0][3:] == before[0][3:] and after[1:] == before[1:]
    assert save(client, card_id='5').status_code == 404
    assert save(client, card_id='x').status_code == 400


def test_admin_server_permission_even_with_settings_flag(site):
    app, client, config = site
    with sqlite3.connect(config['DATABASE']) as db:
        db.execute("INSERT INTO staff_users(id,name,email,password_hash,role,can_settings,created_at) VALUES(99,'Gerente','gerente@test.invalid',?,'gerente',1,'2026-10-27')", (generate_password_hash('local-test'),))
    with client.session_transaction() as session:
        session.clear()
        session.update(staff='staff',staff_user_id=99,staff_session_version=1)
    assert client.get(PATH).status_code == 403
    assert save(client, picture()).status_code == 403
    assert 'Cartões explicativos' not in client.get('/painel/configuracoes').text
    with sqlite3.connect(config['DATABASE']) as db:
        db.execute("UPDATE staff_users SET role='administrador' WHERE id=99")
    assert client.get(PATH).status_code == 200
    assert save(client, picture()).status_code == 200
    anonymous = app.test_client()
    assert anonymous.get(PATH).status_code == 302
    assert anonymous.post(PATH, data={'csrf_token':csrf(anonymous)}).status_code == 302
