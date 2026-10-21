"""Envio real de códigos; nunca simula sucesso sem credenciais."""
import json, os, smtplib
from email.message import EmailMessage
from urllib.request import Request, urlopen


def send_code(channel, destination, code):
    message = f"Seu código de confirmação do Ponto de Coleta Adelinha é {code}. Ele expira em 10 minutos."
    if channel == "email":
        required = [os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"), os.getenv("SMTP_FROM")]
        if not all(required): return False, "E-mail não configurado"
        mail = EmailMessage(); mail["From"], mail["To"], mail["Subject"] = required[3], destination, "Código de confirmação"
        mail.set_content(message)
        with smtplib.SMTP_SSL(required[0], int(os.getenv("SMTP_PORT", "465")), timeout=20) as server:
            server.login(required[1], required[2]); server.send_message(mail)
        return True, "aceito pelo servidor SMTP"
    if channel == "whatsapp":
        token, phone_id = os.getenv("WHATSAPP_ACCESS_TOKEN"), os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        if not token or not phone_id: return False, "WhatsApp não configurado"
        payload = json.dumps({"messaging_product":"whatsapp","to":destination,"type":"text","text":{"body":message}}).encode()
        req = Request(f"https://graph.facebook.com/v21.0/{phone_id}/messages", data=payload,
                      headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"})
        with urlopen(req, timeout=20) as response:
            return 200 <= response.status < 300, "aceito pelo provedor"
    return False, "Canal inválido"


def send_email(destination, subject, body):
    required = [os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"), os.getenv("SMTP_FROM")]
    if not all(required): return False, "E-mail não configurado"
    mail = EmailMessage(); mail["From"], mail["To"], mail["Subject"] = required[3], destination, subject
    mail.set_content(body)
    with smtplib.SMTP_SSL(required[0], int(os.getenv("SMTP_PORT", "465")), timeout=20) as server:
        server.login(required[1], required[2]); server.send_message(mail)
    return True, "aceito pelo servidor SMTP"
