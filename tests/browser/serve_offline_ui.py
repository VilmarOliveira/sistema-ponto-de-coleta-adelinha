"""Synthetic operator for real-browser offline tests. Never installed as an app route."""
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from flask import redirect,session,request
import app as application
from app import create_app
from database import DatabaseConnection
from test_app import register
application.send_code=lambda *a,**k:(False,'offline browser fixture')
TEMP=tempfile.TemporaryDirectory()
app=create_app({'TESTING':True,'SECRET_KEY':'offline-browser-fixture','DATABASE':str(Path(TEMP.name)/'offline.db')})
@app.before_request
def simulate_unavailable():
    if request.path=='/offline/' and request.args.get('fixture_unavailable')=='1':
        return 'Synthetic server unavailable',503

@app.get('/__offline_fixture__')
def offline_fixture_login():
    session.clear();session.update(staff='Operador Fictício',staff_user_id=1,staff_session_version=1,csrf_token='offline-fixture')
    return redirect('/offline/')
@app.get('/__offline_vectors__')
def offline_vectors():
    from core import pix_payload
    return dict(vectors=[dict(key='00000000000000',receiver_name=name,amount=value,payload=pix_payload('00000000000000',name,value))
        for name,value in [('RECEBEDOR TESTE',4.9),('JOÃO DA SILVA',14.8),('TESTE',0.01),('TESTE',1000)]])

@app.get('/__offline_counts__')
def offline_counts():
    connection=DatabaseConnection(app.config['DATABASE'])
    result=dict(packages=connection.execute('SELECT COUNT(*) n FROM packages').fetchone()['n'],
        pickups=connection.execute('SELECT COUNT(*) n FROM pickups').fetchone()['n'],
        note=connection.execute('SELECT payment_note FROM pickups ORDER BY id DESC LIMIT 1').fetchone())
    result['note']=result['note']['payment_note'] if result['note'] else None
    connection.close()
    return result

client=app.test_client();register(client)
db=DatabaseConnection(app.config['DATABASE'])
db.execute("""INSERT INTO staff_users(id,public_id,name,email,password_hash,role,created_at)
 VALUES(1,'ADMPCA-1','Operador Fictício','fixture@example.test','unused','administrador',?)""",(datetime.now(timezone.utc).isoformat(),))
db.execute("""INSERT INTO packages(id,public_id,client_id,tracking,width,height,length,weight,shelf,category,base_price,status,created_at,notified_at)
 VALUES(1,'PCTPCA-1',1,'FIXTURE0001',10,10,10,1,'A1','Pequeno',4.9,'aguardando_retirada',?,?)""",(datetime.now(timezone.utc).isoformat(),datetime.now(timezone.utc).isoformat()))
db.execute("UPDATE settings SET pix_key='00000000000000',pix_receiver_name='RECEBEDOR TESTE',pix_key_type='CNPJ' WHERE id=1")
db.commit();db.close()

if __name__=='__main__':
    app.run('127.0.0.1',5096,threaded=True)
