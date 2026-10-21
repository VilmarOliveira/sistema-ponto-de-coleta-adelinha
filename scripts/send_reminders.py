"""Job idempotente para executar diariamente por Render Cron ou GitHub Actions agendado."""
import os
from collections import defaultdict
from datetime import datetime, timedelta
from core import TZ
from database import DatabaseConnection
from notifications import send_email

url=os.environ.get('DATABASE_URL')
if not url: raise SystemExit('DATABASE_URL não configurada')
db=DatabaseConnection(url); today=datetime.now(TZ).date(); target=today-timedelta(days=2)
rows=db.execute("""SELECT p.id,p.public_id,p.tracking,p.notified_at,c.name,c.email FROM packages p JOIN clients c ON c.id=p.client_id
 WHERE p.status='aguardando_retirada' AND p.forwarded_at IS NULL AND p.notified_at IS NOT NULL AND p.reminder_sent_at IS NULL AND c.email IS NOT NULL""").fetchall()
groups=defaultdict(list)
for row in rows:
    if datetime.fromisoformat(row['notified_at']).astimezone(TZ).date()==target: groups[(row['name'],row['email'])].append(row)
for (name,email), packages in groups.items():
    eligible=[]
    for p in packages:
        current=db.execute("SELECT status,reminder_sent_at FROM packages WHERE id=?",(p['id'],)).fetchone()
        if current and current['status']=='aguardando_retirada' and not current['reminder_sent_at']: eligible.append(p)
    if not eligible: continue
    deadline=target+timedelta(days=3)
    listing='\n'.join(f"- {p['public_id']} · rastreio {p['tracking']}" for p in eligible)
    body=f"Olá, {name}!\n\n{listing}\n\nRetire até {deadline.strftime('%d/%m/%Y')} para evitar taxa adicional de R$ 0,50 por dia corrido e pacote.\nEndereço: Rua Afonso Borges de Freitas, 795, Jardim Adelinha, Franca – SP.\nHorários: segunda a sexta, 09h–20h; sábado, 09h–12h."
    try: sent,status=send_email(email,'Seu prazo de retirada está terminando',body)
    except Exception as exc: sent,status=False,type(exc).__name__
    for p in eligible:
        db.execute("INSERT INTO reminder_logs(package_id,channel,status,created_at) VALUES(?,?,?,?)",(p['id'],'email',status,datetime.now(TZ).isoformat()))
        if sent: db.execute("UPDATE packages SET reminder_sent_at=? WHERE id=? AND reminder_sent_at IS NULL",(datetime.now(TZ).isoformat(),p['id']))
    db.commit()
db.close()
