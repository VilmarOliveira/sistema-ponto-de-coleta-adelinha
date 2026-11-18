"""Apply compatible offline operations using existing prices, reservations and plan rules."""
import json
import hashlib
import re
from datetime import datetime, timedelta
from decimal import Decimal
from core import TZ, calculate_fees, classify_package, pix_payload, valid_cpf
from client_compliance import signature_data, valid_email, revision_id
import client_actions
import plan_service
import pickup_payments


def insert(db,table,values):
    keys=list(values)
    return db.execute('INSERT INTO '+table+'('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+') RETURNING id',
                      tuple(values[k] for k in keys)).fetchone()['id']


def resolve(db,ref,kind,operator_id):
    if ref.startswith('srv:'):
        return int(ref[4:])
    row=db.execute("SELECT linked_id FROM offline_operations WHERE id=? AND kind=? AND operator_id=? AND state='linked'",
                   (ref,kind,operator_id)).fetchone()
    if not row:
        raise ValueError('Conclua a validação do cliente ou a importação do pacote anterior e tente sincronizar novamente.')
    return row['linked_id']


def fees(db,p,at):
    total=calculate_fees(p['base_price'],p['notified_at'],p['picked_at'],at.date())
    paid,settled=pickup_payments.prepaid(db,p['id'])
    base=max(0,round(total['base']-settled,2));due=max(0,round(total['total']-settled,2))
    total.update(base=base,late_fee=round(due-base,2),total=due,prepaid=paid)
    return total


def apply(db,event,staff,now,revision,contract=None):
    data=event['data'];kind=event['kind']
    occurred=datetime.fromisoformat(event['created_at'].replace('Z','+00:00')).astimezone(TZ)
    if occurred<now-timedelta(days=8) or occurred>now+timedelta(minutes=10):
        raise ValueError('Data fora da janela automática de oito dias. Confira o registro manualmente.')
    actor=staff['public_id'] or staff['name']
    if kind=='client':
        from app import next_public_code
        from branding import BRAND_VERSION, ORIGINAL_LOGO
        cpf=data.get('cpf','')
        if not valid_cpf(cpf):
            raise ValueError('Confira o CPF do cliente.')
        if db.postgres:
            db.execute('SELECT pg_advisory_xact_lock(?)',(int(hashlib.sha256(('offline-client:'+cpf).encode()).hexdigest()[:15],16),))
        row=db.execute("SELECT * FROM clients WHERE REPLACE(REPLACE(REPLACE(cpf,'.',''),'-',''),' ','')=?",(cpf,)).fetchone()
        if row:
            if not row['active'] or row['name'].strip().casefold()!=data['name'].strip().casefold() or (row['email'] or '').lower()!=data.get('email','').lower():
                raise ValueError('CPF já cadastrado com dados divergentes ou inativo. Confira o vínculo existente.')
            return kind,row['id'],'Cliente '+row['public_id']+' vinculado; cadastro existente preservado.'
        if data.get('registration_version')!=2 or data.get('terms_accept')!='yes' or not signature_data(data.get('signature','')):
            raise ValueError('Cadastro antigo ou incompleto: confira endereço, aceite e assinatura antes de importar.')
        required=('residential_street','residential_number','residential_district','residential_city')
        if len(data['name'])<5 or len(re.sub(r'\D','',data['phone']))<10 or not data.get('email') or not valid_email(data['email']) or len(re.sub(r'\D','',data.get('residential_cep','')))!=8 or not re.fullmatch('[A-Za-z]{2}',data.get('residential_state','')) or not all(data.get(k) for k in required):
            raise ValueError('Confira os dados obrigatórios do cadastro offline.')
        version,label,body=contract
        digest=hashlib.sha256(body.encode()).hexdigest()
        if data['contract_version']!=version or data['contract_digest']!=digest:
            raise ValueError('Contrato mudou. Confira o aceite da versão vigente antes de importar o cliente.')
        public=next_public_code(db,'CLIPCA')
        values=dict(public_id=public,name=data['name'],cpf=cpf,phone=re.sub(r'\D','',data['phone']),email=data['email'].lower(),
            terms_version=version,terms_text=body,signature=data['signature'],accepted_at=occurred.isoformat(),password_hash=None,
            contract_public_id=public,document_brand_version=BRAND_VERSION,document_logo_present=int(ORIGINAL_LOGO.is_file()),
            confirmation_channel='offline',confirmation_destination=None,confirmation_validated_at=None,
            terms_display_label=label,contract_revision_id=revision_id(version,body),
            contract_hash=hashlib.sha256((public+data['name']+cpf+body+data['signature']+occurred.isoformat()).encode()).hexdigest())
        values.update({k:v for k,v in data.items() if k.startswith('residential_')})
        ident=insert(db,'clients',values)
        db.execute('UPDATE clients SET contract_id=? WHERE id=?',('CTRPCA-'+str(ident),ident))
        return kind,ident,'Cliente '+public+' criado. Confirmação do e-mail e criação da senha pendentes.'
    if kind=='package':
        client_id=resolve(db,data['client_ref'],'client',staff['id'])
        owner=db.execute('SELECT * FROM clients WHERE id=? AND active=1',(client_id,)).fetchone()
        if not owner:
            raise ValueError('Cliente inativo ou inexistente.')
        # Import records already performed offline without claiming that pending
        # email/password regularization was completed. Explicit unrelated blocks stay.
        from client_compliance import diagnostics
        offline_client=db.execute("SELECT id FROM offline_operations WHERE kind='client' AND state='linked' AND linked_id=? AND operator_id=?",(client_id,staff['id'])).fetchone()
        deferred=bool(offline_client and owner['confirmation_channel']=='offline' and
            {x['key'] for x in diagnostics(owner)}<={'email_confirmation','password'})
        blockers=[]
        for requirement in client_actions.client_items(db,owner,now.isoformat(),commit_assignments=False):
            if requirement['kind']!='mandatory' or requirement['status']!='published' or 'new_packages' not in requirement['functions']:continue
            exact_contract=requirement['is_contract'] and requirement['require_existing'] and requirement['document_version']==owner['terms_version'] and requirement['body']==owner['terms_text']
            validation_only=requirement['criterion']=='email_confirmation' or (requirement['criterion']=='profile' and not requirement['is_contract'])
            if not (deferred and (exact_contract or validation_only)):blockers.append(requirement['title'])
        if blockers:
            raise ValueError('Cliente precisa regularizar: '+'; '.join(blockers))
        if db.execute('SELECT id FROM packages WHERE UPPER(tracking)=?',(data['tracking'],)).fetchone():
            raise ValueError('Rastreio já existente. Confira e vincule o pacote existente; não será criado outro.')
        category,price=classify_package(*(data[k] for k in ('width','height','length','weight')))
        plan_service.lock_account(db,client_id,occurred)
        pid=insert(db,'packages',dict(client_id=client_id,tracking=data['tracking'],
            width=data['width'],height=data['height'],length=data['length'],weight=data['weight'],shelf=data['shelf'],
            category=category,base_price=price,status='aguardando_aviso',created_at=occurred.isoformat(),
            offline_operation_id=event['id']))
        public='PCTPCA-'+str(pid);db.execute('UPDATE packages SET public_id=? WHERE id=?',(public,pid))
        covered=plan_service.consume(db,client_id,pid,public,category,price,occurred)
        if bool(data.get('plan_covered',False))!=bool(covered):
            raise ValueError('Cobertura do plano mudou. Confira os créditos antes de importar o pacote.')
        if covered and data.get('plan_cycle_id'):
            entry=plan_service.coverage(db,pid)
            if entry['cycle_id']!=data['plan_cycle_id']:
                raise ValueError('Ciclo do plano mudou. Confira o recebimento.')
        return kind,pid,'Pacote '+public+' importado.'
    if kind=='notify':
        pid=resolve(db,data['package_ref'],'package',staff['id'])
        row=db.execute('SELECT * FROM packages WHERE id=?'+(' FOR UPDATE' if db.postgres else ''),(pid,)).fetchone()
        if not row or row['status']=='retirado':
            raise ValueError('Pacote indisponível para aviso.')
        if row['notified_at']:
            return kind,pid,'Aviso anterior preservado.'
        if datetime.fromisoformat(row['created_at']).astimezone(TZ)>occurred:
            raise ValueError('Aviso anterior ao recebimento. Confira o relógio e as datas.')
        if data['package_ref'].startswith('srv:') and revision(row)!=data['revision']:
            raise ValueError('Pacote alterado; confira o aviso.')
        if not db.execute('SELECT operation_id FROM offline_notice_confirmations WHERE operation_id=?',(event['id'],)).fetchone():
            raise ValueError('Envie o aviso ao cliente e confirme o envio para continuar a sincronização.')
        db.execute("UPDATE packages SET status='aguardando_retirada',notified_at=? WHERE id=?",(occurred.isoformat(),pid))
        return kind,pid,'Aviso de chegada registrado; prazo iniciado na data original.'
    if data['payment_method'] not in ('Pix AI','Dinheiro'):
        raise ValueError('Registro antigo de conferência manual: revise a modalidade antes de vincular.')
    ids=[resolve(db,ref,'package',staff['id']) for ref in data['package_refs']]
    if len(ids)!=len(set(ids)):
        raise ValueError('A seleção aponta duas vezes ao mesmo pacote.')
    marks=','.join('?' for _ in ids)
    packages=db.execute('SELECT * FROM packages WHERE id IN ('+marks+') ORDER BY id'+(' FOR UPDATE' if db.postgres else ''),tuple(ids)).fetchall()
    if len(packages)!=len(ids) or any(p['status']!='aguardando_retirada' for p in packages):
        raise ValueError('Pacote já retirado ou indisponível. Confira o comprovante existente.')
    if len({p['client_id'] for p in packages})!=1:
        raise ValueError('Registre separadamente as retiradas de clientes diferentes.')
    if any(datetime.fromisoformat(p['created_at']).astimezone(TZ)>occurred or
           (p['notified_at'] and datetime.fromisoformat(p['notified_at']).astimezone(TZ)>occurred) for p in packages):
        raise ValueError('Retirada anterior ao recebimento ou aviso. Confira as datas antes de importar.')
    by_id={p['id']:p for p in packages}
    for ref in data['package_refs']:
        if ref.startswith('srv:'):
            p=by_id[int(ref[4:])]
            matches=revision(p)==data['revisions'][ref]
            if not matches and p['status']=='aguardando_retirada':
                previous=dict(p);previous.update(status='aguardando_aviso',notified_at=None)
                notices=db.execute("SELECT payload FROM offline_operations WHERE kind='notify' AND state='linked' AND linked_id=? AND operator_id=?",(p['id'],staff['id'])).fetchall()
                matches=revision(previous)==data['revisions'][ref] and any(
                    datetime.fromisoformat(json.loads(n['payload'])['created_at'].replace('Z','+00:00')).astimezone(TZ).isoformat()==p['notified_at'] for n in notices)
            if p['status']!='aguardando_retirada' or not matches:
                raise ValueError('Pacote alterado desde a preparação. Confira valores e status.')
    if db.execute('SELECT package_id FROM pickup_packages WHERE package_id IN ('+marks+') LIMIT 1',tuple(ids)).fetchone():
        raise ValueError('Um dos pacotes já possui comprovante de retirada.')
    pickup_payments.assert_unreserved(db,ids)
    snapshot=pickup_payments.quote(packages,data,lambda p:fees(db,p,occurred))
    final=snapshot['final_total']
    if abs(Decimal(str(final))-Decimal(str(data['amount'])))>=Decimal('0.01'):
        raise ValueError('Valor recebido difere do saldo revalidado no horário da retirada. Confira acréscimos, descontos, plano e pagamentos anteriores.')
    if not signature_data(data['signature']):
        raise ValueError('Confira a assinatura.')
    doc=re.sub(r'\D','',data['document'])
    if (data['document_type']=='CPF' and not valid_cpf(doc)) or (data['document_type']=='CNH' and len(doc)!=11):
        raise ValueError('Confira o documento do recebedor.')
    setting=db.execute('SELECT pix_key,pix_receiver_name,pix_key_type FROM settings WHERE id=1').fetchone()
    pix=data.get('pix')
    if data['payment_method']=='Pix AI' and final>0:
        if not pix or setting['pix_key_type']!='CNPJ' or pix['key']!=setting['pix_key'] or pix['receiver_name']!=setting['pix_receiver_name']:
            raise ValueError('Chave ou titular Pix mudou. Confira o recebimento antes de importar.')
        expected=pix_payload(pix['key'],pix['receiver_name'],final)
        if pix.get('payload')!=expected:
            raise ValueError('Código Pix não corresponde ao valor e recebedor.')
    values=dict(receiver_name=data['receiver_name'],receiver_document=data['document'],document_type=data['document_type'],
        signature=data['signature'],staff=staff['name'],picked_at=occurred.isoformat(),
        base_total=sum(p['base'] for p in snapshot['packages']),late_total=sum(p['late_fee'] for p in snapshot['packages']),
        total_paid=final,payment_method=data['payment_method'],payment_confirmed=1,
        payment_confirmed_at=occurred.isoformat(),payment_confirmed_by=actor,
        surcharge_amount=snapshot['surcharge_amount'],surcharge_reason=snapshot['surcharge_reason'],
        surcharge_applied_by=actor,discount_type=snapshot['discount_type'],discount_input=snapshot['discount_input'],
        discount_amount=snapshot['discount_amount'],original_total=snapshot['original_total'],final_total=final,discount_applied_by=actor,
        payment_status='paid_manual' if final else 'zero_total',payment_note=data.get('payment_note',data.get('notes','')),
        offline_operation_id=event['id'],recorded_offline_at=occurred.isoformat())
    if data['payment_method']=='Pix AI':
        values.update(pix_key_snapshot=setting['pix_key'],pix_receiver_snapshot=setting['pix_receiver_name'],pix_key_type_snapshot=setting['pix_key_type'])
    from branding import BRAND_VERSION, ORIGINAL_LOGO
    values.update(document_brand_version=BRAND_VERSION,document_logo_present=int(ORIGINAL_LOGO.is_file()))
    pickup_id=insert(db,'pickups',values)
    for p,total in zip(packages,snapshot['packages']):
        owner=db.execute('SELECT name,public_id FROM clients WHERE id=?',(p['client_id'],)).fetchone()
        columns=dict(pickup_id=pickup_id,package_id=p['id'],base_amount=total['base'],late_amount=total['late_fee'],
            package_public_id=p['public_id'],client_id=p['client_id'],client_name=owner['name'],client_public_id=owner['public_id'],
            tracking_code=p['tracking'],package_category=p['category'],notified_at=p['notified_at'],service_amount=total['base'],
            late_days=total['late_days'],total_amount=total['total'],prepaid_amount=pickup_payments.prepaid(db,p['id'])[0])
        keys=list(columns);db.execute('INSERT INTO pickup_packages('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',tuple(columns[k] for k in keys))
        db.execute("UPDATE packages SET status='retirado',picked_at=? WHERE id=?",(occurred.isoformat(),p['id']))
    return kind,pickup_id,'Retirada CMPPCA-'+str(pickup_id)+' importada; pagamento conferido manualmente.'
