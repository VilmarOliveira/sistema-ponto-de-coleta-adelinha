"""Cria clientes e pacotes fictícios para demonstração, sem apagar dados existentes."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import DatabaseConnection, create_app

app = create_app()
with app.test_request_context("/"):
    db = DatabaseConnection(app.config["DATABASE"])
    existing = db.execute("SELECT id FROM clients WHERE cpf='00000000000'").fetchone()
    if not existing:
        client_id = db.execute("INSERT INTO clients(public_id,name,cpf,phone,terms_version,signature,accepted_at) VALUES(NULL,'Ana Demonstração','00000000000','16999990000','MINUTA-TESTE-v1','data:image/png;base64,TESTE',?) RETURNING id", (datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(),)).fetchone()["id"]
        db.execute("UPDATE clients SET public_id=? WHERE id=?", (f"CLTPCA-{client_id}", client_id))
        package_id = db.execute("INSERT INTO packages(public_id,client_id,width,height,length,weight,shelf,category,base_price,status,created_at,notified_at) VALUES(NULL,?,20,20,20,2,'A-01','Pequeno',5,'aguardando_retirada',?,?) RETURNING id", (client_id, (datetime.now(ZoneInfo("America/Sao_Paulo"))-timedelta(days=5)).isoformat(), (datetime.now(ZoneInfo("America/Sao_Paulo"))-timedelta(days=5)).isoformat())).fetchone()["id"]
        db.execute("UPDATE packages SET public_id=? WHERE id=?", (f"PCTPCA-{package_id}", package_id))
        db.commit()
        print("Dados fictícios criados.")
    else:
        print("Dados de demonstração já existem.")
    db.close()
