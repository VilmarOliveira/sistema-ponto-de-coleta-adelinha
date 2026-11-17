"""Apply compatible offline operations using existing prices, reservations and plan rules."""
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from core import TZ, calculate_fees, classify_package, pix_payload, valid_cpf
from client_compliance import signature_data
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


def apply(db,event,staff,now,revision):
    data=event['data'];kind=event['kind']
    occurred=datetime.fromisoformat(event['created_at'].replace('Z','+00:00')).astimezone(TZ)
    if occurred<now-timedelta(days=8) or occurred>now+timedelta(minutes=10):
        raise ValueError('Data fora da janela automática de oito dias. Confira o registro manualmente.')
    actor=staff['public_id'] or staff['name']
    if kind=='client':
        cpf=data.get('cpf','')
        if not valid_cpf(cpf):
            raise ValueError('Confira o CPF e conclua a validação do cadastro online.')
        row=db.execute('SELECT * FROM clients WHERE cpf=?',(cpf,)).fetchone()
        if not row or not row['active'] or row['name'].strip().casefold()!=data['name'].strip().casefold():
            raise ValueError('Cadastro novo ou divergente: conclua a confirmação de e-mail e contrato online, depois sincronize novamente.')
        return kind,row['id'],'Cliente '+row['public_id']+' vinculado.'
    if kind=='package':
        client_id=resolve(db,data['client_ref'],'client',staff['id'])
        owner=db.execute('SELECT * FROM clients WHERE id=? AND active=1',(client_id,)).fetchone()
        if not owner:
            raise ValueError('Cliente inativo ou inexistente.')
        blockers=client_actions.blockers(db,owner,now.isoformat())['new_packages']
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
        if data['package_ref'].startswith('srv:') and revision(row)!=data['revision']:
            raise ValueError('Pacote alterado; confira o aviso.')
        db.execute("UPDATE packages SET status='aguardando_retirada',notified_at=? WHERE id=?",(occurred.isoformat(),pid))
        return kind,pid,'Aviso de chegada registrado; prazo iniciado na data original.'
    if data['payment_method'] not in ('Pix AI','Dinheiro'):
        raise ValueError('Registro antigo de conferência manual: revise a modalidade antes de vincular.')
    ids=[resolve(db,ref,'package',staff['id']) for ref in data['package_refs']]
    if len(ids)!=len(set(ids)):
        raise ValueError('A seleção aponta duas vezes ao mesmo pacote.')
    marks=','.join('?' for _ in ids)
    packages=db.execute('SELECT * FROM packages WHERE id IN ('+marks+') ORDER BY id'+(' FOR UPDATE' if db.postgres else ''),tuple(ids)).fetchall()
    if len(packages)!=len(ids) or any(p['status'] not in ('aguardando_aviso','aguardando_retirada') for p in packages):
        raise ValueError('Pacote já retirado ou indisponível. Confira o comprovante existente.')
    if len({p['client_id'] for p in packages})!=1:
        raise ValueError('Registre separadamente as retiradas de clientes diferentes.')
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
