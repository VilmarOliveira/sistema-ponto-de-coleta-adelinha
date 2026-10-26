import base64
import io
import json
import re
import sqlite3
from email import message_from_bytes
from pathlib import Path

import pytest
from PIL import Image

import app as app_module
import notifications
from app import create_app
from branding import BRAND_VERSION, DEFAULT_THEME, ORANGE, TEAL, GRAPHITE, WHITE, contrast, readable_text, theme_variables
from contract_pdf import build_contract_pdf
from receipt_pdf import build_receipt_pdf
from test_app import register, signature
from test_customization import csrf, legacy_login
from test_notifications import gmail_environment, Response
from test_receipt_pdf import withdrawal, package


@pytest.fixture
def brand_app(tmp_path):
    database = str(tmp_path / 'brand.db')
    app = create_app({'TESTING': True, 'SECRET_KEY': 'brand-tests', 'DATABASE': database})
    client = app.test_client()
    legacy_login(client)
    return app, client, database


def test_palette_contrast_and_restore_preserve_saved_custom_theme(brand_app):
    app, client, database = brand_app
    variables = theme_variables()
    assert DEFAULT_THEME['secondary'] == TEAL
    for foreground, background in [(variables['--button-ink'], ORANGE), (variables['--teal'], WHITE), (variables['--teal'], '#eafafa'), (variables['--teal'], '#d1f2f3'),
            (DEFAULT_THEME['link'], WHITE), (GRAPHITE, WHITE), (variables['--muted'], WHITE)]:
        assert contrast(foreground, background) >= 4.5
    for background in ('#888888', '#000000', '#ffffff', '#ff4d00', '#4db6ac', '#7142a8'):
        assert contrast(readable_text(background), background) >= 4.5
    custom = {**DEFAULT_THEME, 'primary': '#7142a8', 'button': '#7142a8'}
    saved = client.post('/painel/configuracoes/aparencia', data={'name': 'Minha identidade', **custom, 'csrf_token': csrf(client)})
    assert saved.status_code == 302
    assert '--orange:#7142a8' in client.get('/').text
    restored = create_app(app.config).test_client()
    legacy_login(restored)
    assert '--orange:#7142a8' in restored.get('/').text
    response = restored.post('/painel/configuracoes/aparencia', data={'action': 'restore', 'csrf_token': csrf(restored)}, follow_redirects=True)
    assert 'Cores padrão restauradas' in response.text
    assert f'--orange:{ORANGE}' in restored.get('/').text
    with sqlite3.connect(database) as db:
        assert json.loads(db.execute('SELECT colors FROM site_themes').fetchone()[0]) == custom


def test_logo_is_served_unchanged_and_uploaded_images_have_priority(brand_app, tmp_path, monkeypatch):
    app, client, database = brand_app
    logo = tmp_path / 'original.png'
    Image.new('RGB', (640, 640), '#4db6ac').save(logo)
    monkeypatch.setattr(app_module, 'ORIGINAL_LOGO', logo)
    assert client.get('/identidade/cabecalho').data == logo.read_bytes()
    assert '<img src="/identidade/cabecalho"' in client.get('/').text
    uploaded = io.BytesIO()
    Image.new('RGB', (1200, 400), '#7142a8').save(uploaded, 'PNG')
    data = uploaded.getvalue()
    assert client.post('/painel/configuracoes/identidade', data={'image': (io.BytesIO(data), 'custom.png'), 'csrf_token': csrf(client)}).status_code == 302
    assert client.get('/identidade/cabecalho').data == data
    assert client.post('/painel/configuracoes/banners', data={'banner_id': '0', 'alt_text': 'Minha arte', 'position': '1', 'active': 'yes', 'image': (io.BytesIO(data), 'banner.png'), 'csrf_token': csrf(client)}).status_code == 302
    create_app(app.config)
    assert client.get('/identidade/banner-principal').data == data
    client.post('/painel/configuracoes/identidade', data={'restore': 'yes', 'csrf_token': csrf(client)})
    assert client.get('/identidade/cabecalho').data == logo.read_bytes()


def test_documents_record_version_and_keep_historical_renderer(brand_app):
    app, client, database = brand_app
    register(client)
    client.post('/pacotes', data={'client_id': 1, 'tracking': 'BRAND001', 'shelf': 'A1', 'width': 10, 'height': 10, 'length': 10, 'weight': 1, 'csrf_token': csrf(client)})
    client.post('/pacotes/1/avisar', data={'csrf_token': csrf(client)})
    client.post('/retiradas', data={'package_ids': '1', 'receiver_name': 'Cliente Teste', 'receiver_document': '52998224725', 'document_type': 'CPF', 'payment_method': 'Dinheiro', 'payment_confirmed': 'yes', 'pickup_signature': signature(), 'csrf_token': csrf(client)})
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT document_brand_version FROM clients').fetchone()[0] == BRAND_VERSION
        assert db.execute('SELECT document_brand_version FROM pickups').fetchone()[0] == BRAND_VERSION
    current = client.get('/comprovantes/1/pacotes/1.pdf').data
    assert b'Montserrat' in current and b'ME GUARDE' in current
    historical = build_receipt_pdf(withdrawal(), [package()], 'Endereço').getvalue()
    assert b'/Helvetica' in historical and b'Montserrat' not in historical and b'ME GUARDE' not in historical
    original_streams = re.findall(rb'stream(.*?)endstream', historical, re.S)
    client.post('/painel/configuracoes/aparencia', data={'name': 'Campanha', **{**DEFAULT_THEME, 'primary': '#000000'}, 'csrf_token': csrf(client)})
    assert re.findall(rb'stream(.*?)endstream', build_receipt_pdf(withdrawal(), [package()], 'Endereço').getvalue(), re.S) == original_streams
    assert re.findall(rb'stream(.*?)endstream', client.get('/comprovantes/1/pacotes/1.pdf').data, re.S) == re.findall(rb'stream(.*?)endstream', current, re.S)
    # Ausência de versão em bases antigas continua significando documento histórico.
    with sqlite3.connect(database) as db:
        db.execute('UPDATE clients SET document_brand_version=NULL')
        db.execute('UPDATE pickups SET document_brand_version=NULL')
    create_app(app.config)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT document_brand_version FROM clients').fetchone()[0] is None
        assert db.execute('SELECT document_brand_version FROM pickups').fetchone()[0] is None


def test_email_has_plain_and_safe_branded_html(monkeypatch):
    gmail_environment(monkeypatch)
    captured = {}
    def fake_open(request, timeout):
        if request.full_url.endswith('/token'):
            return Response({'access_token': 'fake-token'})
        encoded = json.loads(request.data)['raw']
        captured['mail'] = message_from_bytes(base64.urlsafe_b64decode(encoded + '=='))
        return Response({'id': 'fake-message'})
    monkeypatch.setattr(notifications, 'urlopen', fake_open)
    assert notifications.send_email('test@example.com', 'Teste da identidade', 'Seu código é 123456. <script>inseguro</script>')[0]
    mail = captured['mail']
    assert mail.get_content_type() == 'multipart/alternative'
    plain, html = [part.get_payload(decode=True).decode('utf-8') for part in mail.get_payload()]
    assert '123456' in plain and 'ME GUARDE' in plain
    assert ORANGE in html and TEAL in html and GRAPHITE in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'Ponto de Coleta Adelinha' in html


def test_email_embeds_available_original_logo_without_changing_it(monkeypatch, tmp_path):
    gmail_environment(monkeypatch)
    logo = tmp_path / 'logo.png'
    Image.new('RGB', (640, 640), '#4db6ac').save(logo)
    monkeypatch.setattr(notifications, 'ORIGINAL_LOGO', logo)
    captured = {}
    def fake_open(request, timeout):
        if request.full_url.endswith('/token'):
            return Response({'access_token': 'fake-token'})
        captured['mail'] = message_from_bytes(base64.urlsafe_b64decode(json.loads(request.data)['raw'] + '=='))
        return Response({'id': 'fake-message'})
    monkeypatch.setattr(notifications, 'urlopen', fake_open)
    assert notifications.send_email('test@example.com', 'Teste', 'Código 123456')[0]
    parts = list(captured['mail'].walk())
    image = next(part for part in parts if part.get_content_type() == 'image/png')
    assert image['Content-ID'] == '<logo-adelinha>'
    assert image.get_payload(decode=True) == logo.read_bytes()
    assert any('cid:logo-adelinha' in part.get_payload(decode=True).decode('utf-8') for part in parts if part.get_content_type() == 'text/html')
