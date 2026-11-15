"""Staging guards use fake credentials and local SQLite, never external calls."""
import sqlite3
from pathlib import Path
import pytest
from app import create_app
from environment_mode import database_fingerprint
from fastflow_gateway import Settings, FastFlow, GatewayError
import notifications
from scripts.prepare_test_environment import prepare
from scripts.prepare_clean_production import PreparationError, read_env


def deny(*a,**k):
    raise AssertionError('external request attempted')


def test_staging_blocks_provider_and_notifications_even_with_credentials(tmp_path,monkeypatch):
    monkeypatch.setattr('requests.request',deny)
    monkeypatch.setattr(notifications,'urlopen',deny)
    for key in ['GMAIL_CLIENT_ID','GMAIL_CLIENT_SECRET','GMAIL_REFRESH_TOKEN','WHATSAPP_ACCESS_TOKEN','WHATSAPP_PHONE_NUMBER_ID','WHATSAPP_TEMPLATE_NAME','WHATSAPP_GRAPH_VERSION']:
        monkeypatch.setenv(key,'fake-configured-value')
    app=create_app({'TESTING':True,'SITE_ENVIRONMENT':'test','DATABASE':str(tmp_path/'stage.db'),
        'FASTFLOW_ENABLED':'1','FASTFLOW_NEW_CHARGES_ENABLED':'1','FASTFLOW_API_KEY':'fake-key',
        'FASTFLOW_WEBHOOK_SECRET':'x'*40,'FASTFLOW_PUBLIC_ORIGIN':'https://example.test',
        'GOOGLE_LOGIN_ENABLED':'1','GOOGLE_LOGIN_CLIENT_SECRET':'fake-secret'})
    assert app.config['FASTFLOW_ENABLED']=='0' and app.config['FASTFLOW_API_KEY']==''
    assert app.config['GOOGLE_LOGIN_ENABLED']=='0'
    assert app.config['SESSION_COOKIE_NAME']=='ponto_coleta_teste'
    with app.app_context():
        from app import qr_code_data_url
        from payment_policies import local_code
        assert qr_code_data_url('old-real-pix-fixture') is None
        assert local_code(None,'Pix AI',490) is None
        assert notifications.notification_config_status()=={'email':False,'whatsapp':False}
        assert notifications.send_email('example@example.test','subject','body')[0] is False
        assert notifications.send_code('email','example@example.test','123456')[0] is False
        assert notifications._send_whatsapp('16999999999','123456')[0] is False
        assert notifications._gmail_access_token()[0] is None
        direct=FastFlow(Settings('fake','x'*40,'https://example.test',True))
        for method,path in [('GET','/transactions/1'),('POST','/transactions')]:
            with pytest.raises(GatewayError,match='desativada'):
                direct.request(method,path)
    response=app.test_client().get('/')
    assert 'AMBIENTE DE TESTES' in response.text
    assert response.headers['X-Site-Environment']=='test'
    assert 'noindex' in response.headers['X-Robots-Tag']
    assert 'ponto_coleta_teste=' in response.headers.get('Set-Cookie','')
    assert app.debug is False


def test_guard_refuses_production_database_before_initialization(tmp_path):
    file=tmp_path/'production.db'
    with pytest.raises(RuntimeError,match='coincide'):
        create_app({'TESTING':True,'SITE_ENVIRONMENT':'test','DATABASE':str(file),
            'STAGING_PRODUCTION_FINGERPRINT':database_fingerprint(str(file))})
    assert not file.exists()
    with pytest.raises(RuntimeError,match='separação'):
        create_app({'SITE_ENVIRONMENT':'test','DATABASE':str(file)})
    assert not file.exists()


def test_production_defaults_are_preserved(tmp_path):
    app=create_app({'TESTING':True,'DATABASE':str(tmp_path/'prod.db'),
        'FASTFLOW_ENABLED':'1','FASTFLOW_API_KEY':'fixture','FASTFLOW_WEBHOOK_SECRET':'x'*40,
        'FASTFLOW_PUBLIC_ORIGIN':'https://example.test'})
    assert app.config['FASTFLOW_ENABLED']=='1'
    assert app.config['SESSION_COOKIE_NAME']=='session'
    assert 'AMBIENTE DE TESTES' not in app.test_client().get('/').text
    assert Settings.from_config(app.config).ready


def test_process_level_guard_blocks_jobs(monkeypatch):
    monkeypatch.setenv('SITE_ENVIRONMENT','test')
    monkeypatch.setattr(notifications,'urlopen',deny)
    monkeypatch.setattr('requests.request',deny)
    assert notifications.send_email('fixture@example.test','test','body')[0] is False
    assert notifications.gmail_authorization_status()[0] is False
    assert Settings.from_config({'FASTFLOW_ENABLED':'1'}).active is False
    with pytest.raises(GatewayError):
        FastFlow(Settings('fake','x'*40,'https://example.test',True)).get('1')


def test_prepare_env_separates_databases_and_never_copies_credentials(tmp_path):
    prod=tmp_path/'prod.env'; old=tmp_path/'old.env'; output=tmp_path/'stage.env'
    prod_text='DATABASE_URL="postgresql://a:fake@prod.neon.tech/neondb?sslmode=require"\nSECRET_KEY=production-session-key\nFAST_PIX_API_KEY=production-provider-key\n'
    old_text='DATABASE_URL="postgresql://b:fixture@old-pooler.neon.tech/neondb?sslmode=require"\nGMAIL_REFRESH_TOKEN=old-mail-secret\n'
    prod.write_text(prod_text);old.write_text(old_text)
    assert prepare(prod,old,output)==output
    stage=output.read_text()
    assert 'production-provider-key' not in stage and 'old-mail-secret' not in stage
    assert 'production-session-key' not in stage and 'prod.neon.tech' not in stage
    assert read_env(output)['DATABASE_URL']==read_env(old)['DATABASE_URL']
    assert output.stat().st_mode & 0o777 == 0o600
    assert prod.read_text()==prod_text and old.read_text()==old_text
    assert 'SITE_ENVIRONMENT="test"' in stage and 'FAST_PIX_ENABLED="0"' in stage
    with pytest.raises(PreparationError,match='já existe'):
        prepare(prod,old,output)
    old.write_text(prod_text.replace('prod.neon.tech','prod-pooler.neon.tech'))
    with pytest.raises(PreparationError,match='produção'):
        prepare(prod,old,tmp_path/'other.env')


def test_staging_disallows_legacy_staff_login(tmp_path):
    from werkzeug.security import generate_password_hash
    from test_app import token
    app=create_app({'TESTING':True,'SITE_ENVIRONMENT':'test','DATABASE':str(tmp_path/'stage.db'),
        'STAFF_USER':'fixture','STAFF_PASSWORD_HASH':generate_password_hash('fixture-password')})
    client=app.test_client()
    client.post('/login',data={'user':'fixture','password':'fixture-password','csrf_token':token(client)})
    with client.session_transaction() as session:
        assert not session.get('staff')
