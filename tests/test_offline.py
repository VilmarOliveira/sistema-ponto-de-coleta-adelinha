"""Offline journaling uses local fixtures; never calls payment or email providers."""
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest
from app import create_app
from database import DatabaseConnection
from test_app import register, signature, token


@pytest.fixture()
def setup(tmp_path):
    app=create_app({'TESTING':True,'SECRET_KEY':'offline-fixture-only','DATABASE':str(tmp_path/'offline.db')})
    client=app.test_client()
    register(client)
    db=DatabaseConnection(app.config['DATABASE'])
    db.execute("""INSERT INTO staff_users(id,public_id,name,email,password_hash,role,created_at)
        VALUES(1,'ADMPCA-1','Operador Teste','offline@example.test','unused','administrador',?)""",(datetime.now(timezone.utc).isoformat(),))
    db.execute("""INSERT INTO packages(id,public_id,client_id,tracking,width,height,length,weight,shelf,category,base_price,status,created_at,notified_at)
        VALUES(1,'PCTPCA-1',1,'TRACKFIXTURE',10,10,10,1,'A1','Pequeno',4.9,'aguardando_retirada',?,?)""",
        (datetime.now(timezone.utc).isoformat(),datetime.now(timezone.utc).isoformat()))
    db.commit();db.close()
    login(client)
    return app,client


def login(client,ident=1):
    with client.session_transaction() as sess:
        sess.clear();sess.update(staff='Operador Teste',staff_user_id=ident,staff_session_version=1,csrf_token='offline-csrf')


def prepare(client):
    result=client.get('/offline/api/prepare')
    assert result.status_code==200,result.text
    return result.json


def event(kind='client',**data):
    defaults={
        'client':dict(name='Cliente Offline',phone='16999999999',cpf='52998224725',email='offline@example.test',address='Rua de Teste, 1',notes=''),
        'package':dict(client_ref='srv:1',tracking='NEWTRACK',shelf='A1',width=10,height=10,length=10,weight=1,notes=''),
        'pickup':dict(package_refs=['srv:1'],revisions={},receiver_name='Cliente Teste',document_type='CPF',document='52998224725',
                      payment_method='Dinheiro',signature=signature(),amount=4.9,notes='')}
    return dict(id=str(uuid.uuid4()),kind=kind,created_at=datetime.now(timezone.utc).isoformat(),data={**defaults[kind],**data})


def sync(client,snapshot,events,device=None):
    return client.post('/offline/api/sync',data={'csrf_token':token(client),
        'payload':json.dumps(dict(scope=snapshot['scope'],device=device or str(uuid.uuid4()),events=events))})


def query(app,sql,params=()):
    db=DatabaseConnection(app.config['DATABASE'])
    rows=db.execute(sql,params).fetchall();db.close()
    return rows


def test_offline_requires_individual_staff_and_current_permissions(setup):
    app,client=setup
    with client.session_transaction() as s:s.clear()
    assert client.get('/offline/').status_code==302
    with client.session_transaction() as s:s.update(staff='legacy',staff_legacy=True)
    assert client.get('/offline/api/prepare').status_code==403
    login(client)
    db=DatabaseConnection(app.config['DATABASE']);db.execute('UPDATE staff_users SET can_pickups=0 WHERE id=1');db.commit();db.close()
    assert client.get('/offline/api/session').status_code==403


def test_snapshot_is_minimal_private_and_shell_is_generic(setup):
    app,client=setup
    snapshot=prepare(client)
    assert 'cpf' not in snapshot['clients'][0] and 'email' not in snapshot['clients'][0]
    assert len(snapshot['packages'][0]['revision'])==64
    assert 'no-store' in client.get('/offline/api/prepare').headers['Cache-Control']
    shell=client.get('/static/offline/index.html')
    assert b'Cliente Teste' not in shell.data and b'csrf_token' not in shell.data
    worker=client.get('/offline/sw.js')
    assert worker.headers['Service-Worker-Allowed']=='/offline/'
    assert b"startsWith('/offline/api/')" in worker.data


def test_sync_needs_csrf_and_correct_operator_scope(setup):
    app,client=setup
    snapshot=prepare(client)
    assert client.post('/offline/api/sync',data={'payload':'{}'}).status_code==400
    assert sync(client,{**snapshot,'scope':'wrong'},[event()]).status_code==409
    assert not query(app,'SELECT * FROM offline_operations')


def test_retries_are_idempotent_and_do_not_create_business_records(setup):
    app,client=setup;snapshot=prepare(client);entry=event('package');device=str(uuid.uuid4())
    first=sync(client,snapshot,[entry],device);second=sync(client,snapshot,[entry],device)
    assert first.status_code==second.status_code==200
    assert first.json==second.json
    assert len(query(app,'SELECT * FROM offline_operations'))==1
    assert len(query(app,'SELECT * FROM packages'))==1
    assert len(query(app,'SELECT * FROM clients'))==1
    assert not query(app,'SELECT * FROM pickups')
    inbox=client.get('/offline/api/inbox').json
    assert inbox['items'][0]['event']['data']['tracking']=='NEWTRACK'


def test_changed_retry_rolls_back_entire_batch(setup):
    app,client=setup;snapshot=prepare(client);device=str(uuid.uuid4());entry=event()
    assert sync(client,snapshot,[entry],device).status_code==200
    changed={**entry,'data':{**entry['data'],'name':'Different'}}
    assert sync(client,snapshot,[event('package'),changed],device).status_code==409
    assert len(query(app,'SELECT * FROM offline_operations'))==1
    assert sync(client,snapshot,[entry],str(uuid.uuid4())).status_code==409


def test_package_duplicates_and_changed_pickups_remain_conflicts(setup):
    app,client=setup;snapshot=prepare(client)
    duplicate=sync(client,snapshot,[event('package',tracking='TRACKFIXTURE')])
    assert duplicate.json['results'][0]['state']=='conflict'
    pickup=event('pickup',revisions={'srv:1':snapshot['packages'][0]['revision']})
    db=DatabaseConnection(app.config['DATABASE']);db.execute("UPDATE packages SET status='retirado' WHERE id=1");db.commit();db.close()
    result=sync(client,snapshot,[pickup])
    assert result.json['results'][0]['state']=='conflict'
    assert not query(app,'SELECT * FROM pickups')


def test_different_devices_same_tracking_are_flagged(setup):
    app,client=setup;snapshot=prepare(client)
    assert sync(client,snapshot,[event('package')]).json['results'][0]['state']=='review'
    assert sync(client,snapshot,[event('package')]).json['results'][0]['state']=='conflict'


@pytest.mark.parametrize('change',[{'width':151},{'weight':float('nan')},{'weight':-1},{'tracking':'<script>'}])
def test_invalid_package_never_enters_journal(setup,change):
    app,client=setup
    assert sync(client,prepare(client),[event('package',**change)]).status_code==400
    assert not query(app,'SELECT * FROM offline_operations')


def test_no_automatic_pix_or_bad_signatures(setup):
    app,client=setup;snapshot=prepare(client);rev={'srv:1':snapshot['packages'][0]['revision']}
    for changes in ({'payment_method':'Pix Fast'},{'signature':'data:image/png;base64,invalid'},{'amount':-1}):
        assert sync(client,snapshot,[event('pickup',revisions=rev,**changes)]).status_code==400
    assert not query(app,'SELECT * FROM offline_operations')


def test_valid_pickup_is_preserved_for_review_not_automatically_billed(setup):
    app,client=setup;snapshot=prepare(client);rev={'srv:1':snapshot['packages'][0]['revision']}
    result=sync(client,snapshot,[event('pickup',revisions=rev)])
    assert result.status_code==200 and result.json['results'][0]['state']=='review'
    assert query(app,'SELECT status FROM packages')[0]['status']=='aguardando_retirada'
    assert not query(app,'SELECT * FROM pickups')


def test_reconciliation_checks_matching_online_record_and_is_audited(setup):
    app,client=setup;snapshot=prepare(client);entry=event()
    sync(client,snapshot,[entry])
    form=dict(csrf_token=token(client),id=entry['id'],target='CLTPCA-999999',note='Conferido')
    assert client.post('/offline/api/reconcile',data=form).status_code==409
    public=query(app,'SELECT public_id FROM clients WHERE id=1')[0]['public_id']
    form['target']=public
    response=client.post('/offline/api/reconcile',data=form)
    assert response.status_code==200,response.text
    assert response.json['state']=='linked'
    assert client.post('/offline/api/reconcile',data=form).status_code==409
    assert query(app,"SELECT action FROM audit_logs WHERE action='conferir_contingencia'")


def test_another_operator_cannot_read_or_link_journal(setup):
    app,client=setup;snapshot=prepare(client);entry=event();sync(client,snapshot,[entry])
    db=DatabaseConnection(app.config['DATABASE']);db.execute("""INSERT INTO staff_users(id,public_id,name,email,password_hash,role,created_at)
      VALUES(2,'ATEPCA-2','Outro','another@example.test','unused','atendente',?)""",(datetime.now(timezone.utc).isoformat(),));db.commit();db.close()
    login(client,2)
    assert client.get('/offline/api/inbox').json['items']==[]
    assert sync(client,snapshot,[entry]).status_code==409
    assert client.post('/offline/api/reconcile',data=dict(csrf_token=token(client),id=entry['id'],target='1',note='Conferido')).status_code==404


def test_simultaneous_retry_is_not_duplicated(setup):
    app,client=setup;snapshot=prepare(client);entry=event('package');device=str(uuid.uuid4())
    def run(_):
        caller=app.test_client();login(caller)
        return sync(caller,snapshot,[entry],device).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(run,range(2)))==[200,200]
    assert len(query(app,'SELECT * FROM offline_operations'))==1


def test_revoked_session_cannot_sync(setup):
    app,client=setup;snapshot=prepare(client)
    db=DatabaseConnection(app.config['DATABASE']);db.execute('UPDATE staff_users SET session_version=2 WHERE id=1');db.commit();db.close()
    assert sync(client,snapshot,[event()]).status_code==302
    assert not query(app,'SELECT * FROM offline_operations')


def test_postgres_journal_and_concurrent_duplicate_tracking():
    import os
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    psycopg=pytest.importorskip('psycopg')
    url=os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requires PostgreSQL fixture')
    schema='offline_'+uuid.uuid4().hex
    with psycopg.connect(url,autocommit=True) as root:
        root.execute('CREATE SCHEMA '+schema)
    parsed=urlsplit(url)
    scoped=urlunsplit(parsed._replace(query=urlencode(parse_qsl(parsed.query)+[('options','-csearch_path='+schema)])))
    try:
        app=create_app({'TESTING':True,'SECRET_KEY':'pg-offline-fixture','DATABASE':scoped})
        client=app.test_client();register(client)
        db=DatabaseConnection(scoped)
        db.execute("""INSERT INTO staff_users(id,public_id,name,email,password_hash,role,created_at)
            VALUES(1,'ADMPCA-1','Fixture','fixture@example.test','unused','administrador',?)""",(datetime.now(timezone.utc).isoformat(),))
        db.commit();db.close();login(client)
        snapshot=prepare(client)
        def run(_):
            caller=app.test_client();login(caller)
            response=sync(caller,snapshot,[event('package')])
            assert response.status_code==200,response.text
            return response.json['results'][0]['state']
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(run,range(2)))==['conflict','review']
        assert len(query(app,'SELECT * FROM offline_operations'))==2
        assert not query(app,'SELECT * FROM packages')
    finally:
        with psycopg.connect(url,autocommit=True) as root:
            root.execute('DROP SCHEMA '+schema+' CASCADE')


def test_dismissal_preserves_journal_and_audit_but_does_not_block_corrected_record(setup):
    app,client=setup;snapshot=prepare(client);entry=event('package')
    assert sync(client,snapshot,[entry]).status_code==200
    form=dict(csrf_token=token(client),id=entry['id'],note='Registro digitado incorretamente')
    result=client.post('/offline/api/dismiss',data=form)
    assert result.status_code==200 and result.json['state']=='dismissed'
    assert len(query(app,'SELECT * FROM offline_operations'))==1
    assert query(app,"SELECT action FROM audit_logs WHERE action='nao_aplicar_contingencia'")
    assert sync(client,snapshot,[event('package')]).json['results'][0]['state']=='review'
    assert len(query(app,'SELECT * FROM packages'))==1
