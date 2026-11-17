"""Operational synchronization, money and provenance; no real providers."""
import json
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from database import DatabaseConnection
from core import pix_payload
from test_app import token
from test_offline import setup, prepare, event, sync, query, login


def apply(client,snapshot,entries):
    return client.post('/offline/api/import',data={'csrf_token':token(client),
        'payload':json.dumps({'scope':snapshot['scope'],'ids':[x['id'] for x in entries]})})


def modern_pickup(snapshot,**extra):
    return event('pickup',financial_version=2,payment_note='Transferência conferida; referência TESTE',
        surcharge_amount='0',surcharge_reason='',discount_amount='',discount_percent='',
        revisions={'srv:1':snapshot['packages'][0]['revision']},**extra)


def test_compatible_cash_pickup_is_official_with_note_original_date_and_no_replay(setup):
    app,client=setup;snapshot=prepare(client);entry=modern_pickup(snapshot)
    assert sync(client,snapshot,[entry]).status_code==200
    result=apply(client,snapshot,[entry])
    assert result.status_code==200,result.text
    assert result.json['results'][0]['state']=='linked'
    row=query(app,'SELECT * FROM pickups')[0]
    assert row['payment_method']=='Dinheiro' and row['payment_status']=='paid_manual'
    assert row['payment_note'].startswith('Transferência') and row['offline_operation_id']==entry['id']
    assert datetime.fromisoformat(row['picked_at'])==datetime.fromisoformat(entry['created_at'])
    assert query(app,'SELECT status FROM packages')[0]['status']=='retirado'
    assert apply(client,snapshot,[entry]).status_code==200
    assert len(query(app,'SELECT * FROM pickups'))==1
    assert sync(client,snapshot,[entry],query(app,'SELECT device FROM offline_operations')[0]['device']).status_code==200


def test_amount_conflict_does_not_create_pickup_and_remains_retriable(setup):
    app,client=setup;snapshot=prepare(client);entry=modern_pickup(snapshot,amount=99)
    sync(client,snapshot,[entry]);result=apply(client,snapshot,[entry])
    assert result.json['results'][0]['state']=='conflict'
    assert not query(app,'SELECT * FROM pickups')
    assert query(app,'SELECT status FROM packages')[0]['status']=='aguardando_retirada'


def test_manual_pix_import_preserves_receiver_and_never_uses_fast(monkeypatch,setup):
    app,client=setup
    monkeypatch.setattr('requests.request',lambda *a,**k:pytest.fail('Fast must never be called'))
    db=DatabaseConnection(app.config['DATABASE'])
    db.execute("UPDATE settings SET pix_key='00000000000000',pix_receiver_name='RECEBEDOR TESTE',pix_key_type='CNPJ' WHERE id=1");db.commit();db.close()
    snapshot=prepare(client)
    pix=dict(key=snapshot['pix']['key'],receiver_name=snapshot['pix']['receiver_name'])
    pix['payload']=pix_payload(pix['key'],pix['receiver_name'],4.9)
    entry=modern_pickup(snapshot,payment_method='Pix AI',pix=pix)
    assert sync(client,snapshot,[entry]).status_code==200
    result=apply(client,snapshot,[entry])
    assert result.json['results'][0]['state']=='linked',result.text
    row=query(app,'SELECT * FROM pickups')[0]
    assert row['pix_key_snapshot']=='00000000000000'
    assert row['payment_status']=='paid_manual' and row['external_transaction_id'] is None


def test_changed_pix_key_and_reserved_fast_order_require_review(setup):
    app,client=setup;snapshot=prepare(client)
    pix=dict(key=snapshot['pix']['key'],receiver_name=snapshot['pix']['receiver_name'])
    pix['payload']=pix_payload(pix['key'],pix['receiver_name'],4.9)
    entry=modern_pickup(snapshot,payment_method='Pix AI',pix=pix)
    sync(client,snapshot,[entry])
    db=DatabaseConnection(app.config['DATABASE']);db.execute("UPDATE settings SET pix_key='11111111111111' WHERE id=1");db.commit();db.close()
    assert apply(client,snapshot,[entry]).json['results'][0]['state']=='conflict'
    assert not query(app,'SELECT * FROM pickups')


def test_surcharge_then_discount_matches_existing_online_calculation(setup):
    app,client=setup;snapshot=prepare(client)
    entry=modern_pickup(snapshot,amount=5.31)
    entry['data'].update(surcharge_amount='1',surcharge_reason='Serviço extra',discount_percent='10')
    sync(client,snapshot,[entry]);result=apply(client,snapshot,[entry])
    assert result.json['results'][0]['state']=='linked',result.text
    row=query(app,'SELECT * FROM pickups')[0]
    assert row['surcharge_amount']==1 and row['discount_amount']==.59
    assert abs(row['final_total']-5.31)<.001


def test_receive_notify_and_pickup_same_offline_package_resolve_dependencies(setup):
    app,client=setup;snapshot=prepare(client);received=event('package',plan_covered=False,plan_cycle_id=None)
    notice=event('notify',package_ref=received['id'],revision='')
    pickup=modern_pickup(snapshot,package_refs=[received['id']])
    pickup['data']['revisions']={}
    assert sync(client,snapshot,[received,notice,pickup]).status_code==200
    result=apply(client,snapshot,[pickup,notice,received])
    assert all(r['state']=='linked' for r in result.json['results']),result.text
    package=query(app,"SELECT * FROM packages WHERE tracking='NEWTRACK'")[0]
    assert package['status']=='retirado' and package['offline_operation_id']==received['id']
    assert datetime.fromisoformat(package['notified_at'])==datetime.fromisoformat(notice['created_at'])
    assert len(query(app,'SELECT * FROM pickups'))==1


def test_unvalidated_new_client_remains_pending_without_fabricated_consent(setup):
    app,client=setup;snapshot=prepare(client)
    new=event(name='Nome diferente',cpf='52998224725')
    sync(client,snapshot,[new])
    result=apply(client,snapshot,[new])
    assert result.json['results'][0]['state']=='conflict'
    assert len(query(app,'SELECT * FROM clients'))==1


def test_import_requires_csrf_owner_and_matching_environment(setup):
    app,client=setup;snapshot=prepare(client);entry=modern_pickup(snapshot);sync(client,snapshot,[entry])
    assert client.post('/offline/api/import',data={'payload':'{}'}).status_code==400
    assert apply(client,{**snapshot,'scope':'other'},[entry]).status_code==409
    db=DatabaseConnection(app.config['DATABASE']);db.execute('UPDATE staff_users SET can_pickups=0 WHERE id=1');db.commit();db.close()
    assert apply(client,snapshot,[entry]).status_code==403
    assert not query(app,'SELECT * FROM pickups')


def test_payment_note_is_visible_in_official_package_details_and_pdf(setup):
    app,client=setup;snapshot=prepare(client);entry=modern_pickup(snapshot)
    sync(client,snapshot,[entry]);apply(client,snapshot,[entry])
    page=client.get('/painel/pacotes/1')
    # The canonical endpoint can redirect to the detail route on older deployments.
    if page.status_code==404:
        rule=next(r for r in app.url_map.iter_rules() if r.endpoint=='package_detail')
        page=client.get(str(rule).replace('<int:package_id>','1'))
    assert 'Transferência conferida' in page.text
    pid=query(app,'SELECT id FROM pickups')[0]['id']
    pdf=client.get('/comprovantes/'+str(pid)+'/pacotes/1.pdf')
    assert pdf.status_code==200 and pdf.mimetype=='application/pdf'


def test_own_offline_notice_does_not_become_false_revision_conflict(setup):
    app,client=setup
    db=DatabaseConnection(app.config['DATABASE']);db.execute("UPDATE packages SET status='aguardando_aviso',notified_at=NULL WHERE id=1");db.commit();db.close()
    snapshot=prepare(client);notice=event('notify',package_ref='srv:1',revision=snapshot['packages'][0]['revision'])
    pickup=modern_pickup(snapshot)
    sync(client,snapshot,[notice,pickup])
    result=apply(client,snapshot,[notice,pickup])
    assert all(x['state']=='linked' for x in result.json['results']),result.text


def test_fast_reservation_is_not_bypassed_by_cash_offline(setup):
    app,client=setup;snapshot=prepare(client);entry=modern_pickup(snapshot)
    db=DatabaseConnection(app.config['DATABASE']);oid=str(uuid.uuid4());stamp=datetime.now(timezone.utc).isoformat()
    db.execute("""INSERT INTO pickup_payment_orders(id,client_id,amount_cents,state,callback_url,created_at,snapshot,quote_key,created_by)
        VALUES(?,1,490,'pending',?,?,'{}','fixture','fixture')""",(oid,'https://example.test/'+oid,stamp))
    db.execute('INSERT INTO pickup_payment_reservations(package_id,order_id) VALUES(1,?)',(oid,))
    db.commit();db.close()
    sync(client,snapshot,[entry]);result=apply(client,snapshot,[entry])
    assert result.json['results'][0]['state']=='conflict'
    assert not query(app,'SELECT * FROM pickups')


def test_cash_observation_field_is_available_in_online_form(setup):
    app,client=setup
    assert 'name="payment_note"' in client.get('/painel').text


def test_preparation_query_count_does_not_grow_with_client_count(monkeypatch,setup):
    app,client=setup;original=DatabaseConnection.execute;calls=[]
    def counted(self,sql,params=()):
        calls.append(sql)
        return original(self,sql,params)
    monkeypatch.setattr(DatabaseConnection,'execute',counted)
    prepare(client);baseline=len(calls)
    db=DatabaseConnection(app.config['DATABASE']);stamp=datetime.now(timezone.utc).isoformat()
    for i in range(2,22):
        db.execute("INSERT INTO clients(public_id,name,cpf,phone,terms_version,signature,accepted_at) VALUES(?,?,?,?,?,?,?)",
                   ('CLIPCA-'+str(i),'Cliente Fictício '+str(i),'00000000000','00000000000','fixture','fixture',stamp))
    db.commit();db.close();calls.clear()
    assert len(prepare(client)['clients'])==21
    assert len(calls)==baseline


def test_import_preserves_online_requirement_of_notice_before_pickup(setup):
    app,client=setup;snapshot=prepare(client);received=event('package',plan_covered=False)
    pickup=modern_pickup(snapshot,package_refs=[received['id']]);pickup['data']['revisions']={}
    sync(client,snapshot,[received,pickup]);result=apply(client,snapshot,[received,pickup])
    assert [x['state'] for x in result.json['results']]==['linked','conflict']
    assert not query(app,'SELECT * FROM pickups')


def test_inactive_client_can_still_withdraw_existing_packages(setup):
    app,client=setup
    db=DatabaseConnection(app.config['DATABASE']);db.execute('UPDATE clients SET active=0 WHERE id=1');db.commit();db.close()
    snapshot=prepare(client)
    assert snapshot['clients'][0]['active']==0
    entry=modern_pickup(snapshot);sync(client,snapshot,[entry])
    assert apply(client,snapshot,[entry]).json['results'][0]['state']=='linked'
