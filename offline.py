"""Contingency journal. Sync never fabricates consent, API payments or plan credits."""
import hashlib
import hmac
import json
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, abort, jsonify, request, send_from_directory, session
from client_compliance import signature_data
from database import DatabaseIntegrityError


def init_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS offline_operations (
        id TEXT PRIMARY KEY, scope TEXT NOT NULL, operator_id BIGINT NOT NULL REFERENCES staff_users(id),
        device TEXT NOT NULL, kind TEXT NOT NULL, occurred_at TEXT NOT NULL,
        payload TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL,
        reason TEXT NOT NULL, received_at TEXT NOT NULL, linked_type TEXT,
        linked_id BIGINT, reviewed_by BIGINT, reviewed_at TEXT, review_note TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS offline_operation_refs (
        operation_id TEXT NOT NULL REFERENCES offline_operations(id), ref TEXT NOT NULL,
        PRIMARY KEY(operation_id,ref))""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_offline_ref ON offline_operation_refs(ref)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_offline_operator ON offline_operations(operator_id,received_at)")
    db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_offline_link
        ON offline_operations(linked_type,linked_id) WHERE linked_id IS NOT NULL AND linked_type IN ('package','pickup')""")


def package_revision(row):
    return hashlib.sha256(json.dumps(
        {k: row[k] for k in ('id','client_id','tracking','status','notified_at','picked_at','width','height','length','weight','category','base_price','shelf','created_at')},
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def text(data, key, limit=200, required=True):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError('Confira o campo ' + key + '.')
    return value.strip()


def uuid_value(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Identificador local inválido.')


def reference(value):
    if isinstance(value, str) and re.fullmatch(r'srv:[1-9][0-9]{0,11}', value):
        return value
    return uuid_value(value)


def validate_event(event, stamp):
    if not isinstance(event, dict) or not isinstance(event.get('data'), dict):
        raise ValueError('Registro local inválido.')
    eid = uuid_value(event.get('id'))
    kind = event.get('kind')
    raw_date = text(event, 'created_at', 40)
    try:
        date = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
        if date.tzinfo is None or date > stamp + timedelta(minutes=10):
            raise ValueError()
    except ValueError:
        raise ValueError('Data local inválida; confira o relógio do aparelho.')
    data = event['data']
    if kind == 'client':
        clean = {k: text(data,k,n,k in ('name','phone')) for k,n in
                 (('name',160),('phone',30),('cpf',14),('email',254),('address',500),('notes',1000))}
        if clean['cpf'] and not re.fullmatch(r'[0-9]{11}', clean['cpf']):
            raise ValueError('Informe somente os 11 números do CPF.')
    elif kind == 'package':
        clean = {'client_ref': reference(data.get('client_ref')),
                 'tracking': text(data,'tracking',100).upper(),
                 'shelf': text(data,'shelf',30), 'notes': text(data,'notes',1000,False)}
        if not re.fullmatch(r'[A-Za-z0-9]+',clean['tracking']) or not re.fullmatch(r'[A-Za-z0-9]+',clean['shelf']):
            raise ValueError('Rastreio e prateleira devem conter somente letras e números.')
        for key in ('width','height','length','weight'):
            try:
                value = float(data.get(key))
            except (ValueError, TypeError):
                raise ValueError('Confira peso e medidas.')
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Peso e medidas devem ser maiores que zero.')
            clean[key] = value
        if clean['width']+clean['height']+clean['length'] > 150 or clean['weight'] > 20:
            raise ValueError('Limite de 150 cm na soma e 20 kg.')
    elif kind == 'pickup':
        refs = data.get('package_refs')
        revisions = data.get('revisions',{})
        if not isinstance(refs,list) or not 1 <= len(refs) <= 100 or not isinstance(revisions,dict):
            raise ValueError('Selecione os pacotes da retirada.')
        clean = {'package_refs': list(dict.fromkeys(reference(x) for x in refs)),
                 'revisions': {},
                 'receiver_name': text(data,'receiver_name',160),
                 'document_type': text(data,'document_type',3),
                 'document': text(data,'document',30),
                 'payment_method': text(data,'payment_method',30),
                 'signature': text(data,'signature',150000),
                 'notes': text(data,'notes',1000,False)}
        for ref in clean['package_refs']:
            if ref.startswith('srv:'):
                rev = revisions.get(ref)
                if not isinstance(rev,str) or not re.fullmatch(r'[a-f0-9]{64}',rev):
                    raise ValueError('Atualização do pacote não identificada.')
                clean['revisions'][ref] = rev
        if clean['document_type'] not in ('CPF','RG','CNH') or not re.fullmatch(r'[A-Za-z0-9.\-]{5,30}',clean['document']):
            raise ValueError('Confira o documento de quem retirou.')
        if clean['payment_method'] not in ('Dinheiro','Conferência manual'):
            raise ValueError('Pix automático não funciona offline.')
        try:
            amount = float(data.get('amount'))
        except (TypeError,ValueError):
            raise ValueError('Confira o valor recebido.')
        if not math.isfinite(amount) or not 0 <= amount <= 1000000:
            raise ValueError('Confira o valor recebido.')
        clean['amount'] = round(amount,2)
        if not signature_data(clean['signature']):
            raise ValueError('Assinatura de retirada inválida.')
    else:
        raise ValueError('Tipo de registro local inválido.')
    return {'id':eid,'kind':kind,'created_at':raw_date,'data':clean}


def event_references(event):
    if event['kind']=='package':
        return ['tracking:'+event['data']['tracking']]
    if event['kind']=='pickup':
        return ['package:'+x for x in event['data']['package_refs']]
    return []


def conflict_reason(db, event):
    data = event['data']
    for ref in event_references(event):
        if db.execute("""SELECT r.operation_id FROM offline_operation_refs r JOIN offline_operations o ON o.id=r.operation_id
                WHERE r.ref=? AND r.operation_id!=? AND o.state!='dismissed' LIMIT 1""",
                      (ref,event['id'])).fetchone():
            return 'Outro registro de contingência já usa este rastreio ou pacote. Confira duplicidade entre aparelhos.'
    if event['kind'] == 'client':
        if data['cpf'] and db.execute('SELECT id FROM clients WHERE cpf=?',(data['cpf'],)).fetchone():
            return 'CPF já cadastrado. Confira e vincule ao cliente existente.'
    elif event['kind'] == 'package':
        if db.execute('SELECT id FROM packages WHERE UPPER(tracking)=?',(data['tracking'],)).fetchone():
            return 'Rastreio já cadastrado. Não registre o pacote novamente; confira o vínculo.'
        if data['client_ref'].startswith('srv:'):
            client = db.execute('SELECT active FROM clients WHERE id=?',(int(data['client_ref'][4:]),)).fetchone()
            if not client or not client['active']:
                return 'Cliente alterado ou inativo. Regularize antes de concluir.'
    else:
        for ref in data['package_refs']:
            if ref.startswith('srv:'):
                row = db.execute('SELECT * FROM packages WHERE id=?',(int(ref[4:]),)).fetchone()
                if not row or row['status'] == 'retirado' or package_revision(row) != data['revisions'][ref]:
                    return 'Pacote alterado no sistema online. Confira a retirada antes de vincular.'
    return ''


def install(app, db, login_required, current_staff, now):
    bp = Blueprint('offline',__name__,url_prefix='/offline')

    def authorized(view):
        @wraps(view)
        @login_required
        def wrapped(*args,**kwargs):
            staff = current_staff()
            if not staff or not all(staff[k] for k in ('can_clients','can_packages','can_pickups')):
                abort(403,'A contingência exige conta individual com acesso a clientes, pacotes e retiradas.')
            return view(staff,*args,**kwargs)
        return wrapped

    def identity(staff):
        source = str(app.config['DATABASE'])+'|'+str(app.config.get('SITE_ENVIRONMENT','production'))+'|'+str(staff['id'])
        scope = hmac.new(str(app.config['SECRET_KEY']).encode(),source.encode(),hashlib.sha256).hexdigest()
        return {'scope':scope,'operator':staff['public_id'] or str(staff['id']),
                'name':staff['name'],'environment':app.config.get('SITE_ENVIRONMENT','production'),
                'csrf_token':session['csrf_token']}

    @bp.after_request
    def private(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @bp.get('/')
    @authorized
    def page(staff):
        return send_from_directory(app.static_folder+'/offline','index.html')

    @bp.get('/sw.js')
    def worker():
        response=send_from_directory(app.static_folder+'/offline','sw.js')
        response.headers['Service-Worker-Allowed']='/offline/'
        return response

    @bp.get('/api/session')
    @authorized
    def who(staff):
        return jsonify(identity(staff))

    @bp.get('/api/prepare')
    @authorized
    def prepare(staff):
        clients = db().execute('SELECT id,public_id,name,phone FROM clients WHERE active=1 ORDER BY id LIMIT 10001').fetchall()
        packages = db().execute("""SELECT id,public_id,client_id,tracking,category,base_price,status,created_at,notified_at,picked_at,shelf,width,height,length,weight
            FROM packages WHERE status!='retirado' ORDER BY id LIMIT 10001""").fetchall()
        if len(clients)>10000 or len(packages)>10000:
            return jsonify(error='Base muito grande para esta preparação. Solicite preparação por seleção.'),409
        result=identity(staff)
        result.update(prepared_at=now().isoformat(),expires_at=(now()+timedelta(days=7)).isoformat(),
                      clients=[dict(x) for x in clients],
                      packages=[dict(x,revision=package_revision(x)) for x in packages])
        return jsonify(result)

    @bp.post('/api/sync')
    @authorized
    def sync(staff):
        if request.content_length and request.content_length > 4*1024*1024:
            abort(413)
        try:
            value=json.loads(request.form.get('payload',''))
            if not isinstance(value,dict) or value.get('scope')!=identity(staff)['scope']:
                return jsonify(error='Entre com o mesmo operador e ambiente usados na preparação.'),409
            device=uuid_value(value.get('device'))
            events=value.get('events')
            if not isinstance(events,list) or not 1<=len(events)<=20:
                raise ValueError('Envie de 1 a 20 registros por vez.')
            stamp=datetime.now(timezone.utc)
            events=[validate_event(x,stamp) for x in events]
            if len({x['id'] for x in events})!=len(events):
                raise ValueError('Identificadores repetidos no envio.')
        except (ValueError,TypeError) as error:
            return jsonify(error=str(error) or 'Envio inválido.'),400
        connection=db()
        connection.commit()
        connection.begin_write()
        results=[]
        try:
            if connection.postgres:
                refs=sorted({ref for event in events for ref in event_references(event)})
                for ref in refs:
                    lock=int(hashlib.sha256(ref.encode()).hexdigest()[:15],16)
                    connection.execute('SELECT pg_advisory_xact_lock(?)',(lock,))
            for event in events:
                payload=json.dumps(event,ensure_ascii=False,sort_keys=True,separators=(',',':'))
                digest=hashlib.sha256(payload.encode()).hexdigest()
                reason=conflict_reason(connection,event)
                state='conflict' if reason else 'review'
                connection.execute("""INSERT INTO offline_operations
                    (id,scope,operator_id,device,kind,occurred_at,payload,digest,state,reason,received_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
                    (event['id'],value['scope'],staff['id'],device,event['kind'],event['created_at'],
                     payload,digest,state,reason,now().isoformat()))
                row=connection.execute('SELECT * FROM offline_operations WHERE id=?',(event['id'],)).fetchone()
                if row['scope']!=value['scope'] or row['device']!=device or row['digest']!=digest:
                    connection.rollback()
                    return jsonify(error='Identificador já usado com outro conteúdo. Nenhum registro deste envio foi alterado.'),409
                for ref in event_references(event):
                    connection.execute('INSERT INTO offline_operation_refs(operation_id,ref) VALUES(?,?) ON CONFLICT DO NOTHING',(event['id'],ref))
                results.append({'id':row['id'],'state':row['state'],'reason':row['reason']})
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return jsonify(results=results)

    @bp.get('/api/inbox')
    @authorized
    def inbox(staff):
        try:
            after=max(0,int(request.args.get('offset','0')))
        except ValueError:
            abort(400)
        rows=db().execute('SELECT * FROM offline_operations WHERE operator_id=? ORDER BY received_at,id LIMIT 100 OFFSET ?',
                          (staff['id'],after)).fetchall()
        return jsonify(items=[dict(id=r['id'],event=json.loads(r['payload']),state=r['state'],
            reason=r['reason'],linked_type=r['linked_type'],linked_id=r['linked_id'],
            received_at=r['received_at'],review_note=r['review_note']) for r in rows],next_offset=after+100 if len(rows)==100 else None)

    def resolved_client(ref):
        if ref.startswith('srv:'):
            return int(ref[4:])
        row=db().execute("SELECT linked_id FROM offline_operations WHERE id=? AND kind='client' AND state='linked'",(ref,)).fetchone()
        return row['linked_id'] if row else None

    def resolved_package(ref):
        if ref.startswith('srv:'):
            return int(ref[4:])
        row=db().execute("SELECT linked_id FROM offline_operations WHERE id=? AND kind='package' AND state='linked'",(ref,)).fetchone()
        return row['linked_id'] if row else None

    @bp.post('/api/reconcile')
    @authorized
    def reconcile(staff):
        try:
            oid=uuid_value(request.form.get('id'))
            target_code=request.form.get('target','').strip().upper()
            note=request.form.get('note','').strip()
            if not re.fullmatch(r'(?:CLIPCA-|CLTPCA-|PCTPCA-|CMPPCA-)?[0-9]{1,12}',target_code) or len(note)>1000 or not note:
                raise ValueError('Informe o código do registro online e a observação da conferência.')
        except (ValueError,TypeError) as error:
            return jsonify(error=str(error)),400
        connection=db()
        connection.commit();connection.begin_write()
        try:
            row=connection.execute('SELECT * FROM offline_operations WHERE id=?'+(' FOR UPDATE' if connection.postgres else ''),(oid,)).fetchone()
            if not row or row['operator_id']!=staff['id']:
                abort(404)
            if row['state']=='linked':
                connection.rollback()
                return jsonify(error='Registro já vinculado; o histórico foi preservado.'),409
            event=json.loads(row['payload']); data=event['data']; kind=event['kind']
            target=None
            if target_code.isdigit():
                target=int(target_code)
            elif kind in ('client','package'):
                table='clients' if kind=='client' else 'packages'
                match=connection.execute('SELECT id FROM '+table+' WHERE public_id=?',(target_code,)).fetchone()
                target=match['id'] if match else None
            elif re.fullmatch(r'CMPPCA-[0-9]+',target_code):
                target=int(target_code.split('-')[1])
            if not target:
                connection.rollback()
                return jsonify(error='Código online não encontrado.'),409
            if kind=='client':
                actual=connection.execute('SELECT cpf,name,phone FROM clients WHERE id=?',(target,)).fetchone()
                valid=actual and ((data['cpf'] and actual['cpf']==data['cpf']) or
                    (not data['cpf'] and actual['name'].strip().casefold()==data['name'].casefold()
                     and re.sub(r'\D','',actual['phone'])==re.sub(r'\D','',data['phone'])))
            elif kind=='package':
                actual=connection.execute('SELECT tracking,client_id FROM packages WHERE id=?',(target,)).fetchone()
                valid=actual and actual['tracking'].upper()==data['tracking'] and actual['client_id']==resolved_client(data['client_ref'])
            else:
                actual=connection.execute('SELECT receiver_document,total_paid,payment_confirmed FROM pickups WHERE id=?',(target,)).fetchone()
                actual_refs={x['package_id'] for x in connection.execute('SELECT package_id FROM pickup_packages WHERE pickup_id=?',(target,)).fetchall()}
                expected={resolved_package(x) for x in data['package_refs']}
                valid=(actual and actual['payment_confirmed'] and actual_refs==expected and None not in expected
                       and re.sub(r'\W','',actual['receiver_document']).upper()==re.sub(r'\W','',data['document']).upper()
                       and abs(float(actual['total_paid'])-data['amount'])<0.01)
            if not valid:
                connection.rollback()
                return jsonify(error='O registro online não corresponde aos dados locais. Conclua ou confira a operação no fluxo normal antes de vincular.'),409
            exists=connection.execute('SELECT id FROM offline_operations WHERE linked_type=? AND linked_id=?',(kind,target)).fetchone()
            if exists and kind!='client':
                connection.rollback()
                return jsonify(error='Este registro online já está vinculado a uma contingência. Confira duplicidade.'),409
            connection.execute("""UPDATE offline_operations SET state='linked',linked_type=?,linked_id=?,
                reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?""",
                (kind,target,staff['id'],now().isoformat(),note,oid))
            connection.execute("""INSERT INTO audit_logs(actor,action,entity_type,entity_id,details,created_at)
                VALUES(?,?,?,?,?,?)""",(staff['public_id'] or str(staff['id']),'conferir_contingencia',kind,target,oid,now().isoformat()))
            connection.commit()
            return jsonify(state='linked')
        except DatabaseIntegrityError:
            connection.rollback()
            return jsonify(error='Vínculo alterado por outra conferência. Atualize os registros antes de continuar.'),409
        except Exception:
            connection.rollback()
            raise

    @bp.post('/api/dismiss')
    @authorized
    def dismiss(staff):
        try:
            oid=uuid_value(request.form.get('id'))
            note=request.form.get('note','').strip()
            if not note or len(note)>1000:
                raise ValueError('Informe o motivo de não aplicar este registro.')
        except ValueError as error:
            return jsonify(error=str(error)),400
        connection=db();connection.commit();connection.begin_write()
        try:
            row=connection.execute('SELECT * FROM offline_operations WHERE id=?'+(' FOR UPDATE' if connection.postgres else ''),(oid,)).fetchone()
            if not row or row['operator_id']!=staff['id']:
                abort(404)
            if row['state'] in ('linked','dismissed'):
                connection.rollback()
                return jsonify(error='Registro já conferido; histórico preservado.'),409
            connection.execute("UPDATE offline_operations SET state='dismissed',review_note=?,reviewed_by=?,reviewed_at=? WHERE id=?",
                               (note,staff['id'],now().isoformat(),oid))
            connection.execute("""INSERT INTO audit_logs(actor,action,entity_type,details,created_at)
                VALUES(?,?,?,?,?)""",(staff['public_id'] or str(staff['id']),'nao_aplicar_contingencia',row['kind'],oid+': '+note,now().isoformat()))
            connection.commit()
            return jsonify(state='dismissed')
        except Exception:
            connection.rollback()
            raise

    app.register_blueprint(bp)
