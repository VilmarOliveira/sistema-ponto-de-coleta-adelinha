"""Integrações de notificação sem simular sucesso de entrega."""
import json
import os
import re
import smtplib
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def notification_config_status():
    """Retorna o estado da configuração sem expor segredos."""
    security = os.getenv("SMTP_SECURITY", "ssl").strip().lower()
    email_ready = all((os.getenv("SMTP_HOST"), os.getenv("SMTP_FROM"))) and (
        (os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))
        or os.getenv("SMTP_ALLOW_NO_AUTH") == "1"
    ) and security in ("ssl", "starttls", "plain")
    whatsapp_ready = all((os.getenv("WHATSAPP_ACCESS_TOKEN"), os.getenv("WHATSAPP_PHONE_NUMBER_ID"),
                          os.getenv("WHATSAPP_TEMPLATE_NAME"), os.getenv("WHATSAPP_GRAPH_VERSION")))
    return {"email": bool(email_ready), "whatsapp": bool(whatsapp_ready)}


def normalize_whatsapp_destination(destination):
    """Converte números brasileiros locais para E.164, sem o caractere +."""
    value = re.sub(r"\D", "", destination or "")
    if len(value) in (10, 11):
        value = "55" + value
    if not 10 <= len(value) <= 15:
        raise ValueError("número de WhatsApp inválido")
    return value


def _provider_error(error):
    if isinstance(error, HTTPError):
        try:
            body = json.loads(error.read().decode("utf-8", errors="replace"))
            info = body.get("error", {})
            message = str(info.get("message", "erro recusado pelo provedor"))[:240]
            code = info.get("code")
            return f"WhatsApp recusou o envio ({code}): {message}" if code else f"WhatsApp recusou o envio: {message}"
        except Exception:
            return f"WhatsApp recusou o envio (HTTP {error.code})"
    if isinstance(error, URLError):
        return "Não foi possível conectar ao serviço do WhatsApp"
    return f"Falha no provedor: {type(error).__name__}"


def send_email(destination, subject, body):
    host, sender = os.getenv("SMTP_HOST"), os.getenv("SMTP_FROM")
    user, password = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    security = os.getenv("SMTP_SECURITY", "ssl").strip().lower()
    if not host or not sender or (not (user and password) and os.getenv("SMTP_ALLOW_NO_AUTH") != "1"):
        return False, "E-mail não configurado: confira SMTP_HOST, SMTP_FROM e as credenciais"
    if security not in ("ssl", "starttls", "plain"):
        return False, "SMTP_SECURITY deve ser ssl, starttls ou plain"
    try:
        port = int(os.getenv("SMTP_PORT", "465" if security == "ssl" else "587"))
        mail = EmailMessage()
        mail["From"], mail["To"], mail["Subject"] = sender, destination, subject
        mail.set_content(body)
        smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
        with smtp_class(host, port, timeout=20) as server:
            if security == "starttls":
                server.ehlo(); server.starttls(); server.ehlo()
            if user and password:
                server.login(user, password)
            if server.send_message(mail):
                return False, "O servidor SMTP recusou o destinatário"
        return True, "aceito pelo servidor SMTP para processamento"
    except (OSError, smtplib.SMTPException, ValueError) as error:
        return False, f"Falha no envio de e-mail: {type(error).__name__}"


def _send_whatsapp(destination, code):
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    template_name = os.getenv("WHATSAPP_TEMPLATE_NAME")
    version = os.getenv("WHATSAPP_GRAPH_VERSION")
    if not token or not phone_id or not template_name or not version:
        return False, "WhatsApp não configurado: confira token, número, versão da API e modelo aprovado"
    try:
        destination = normalize_whatsapp_destination(destination)
    except ValueError as error:
        return False, str(error)
    # Mensagens iniciadas pela empresa usam um modelo aprovado, inclusive fora
    # da janela de atendimento de 24 horas.
    payload = {"messaging_product": "whatsapp", "to": destination, "type": "template", "template": {
        "name": template_name,
        "language": {"code": os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "pt_BR")},
        "components": [{"type": "body", "parameters": [{"type": "text", "text": code}]}],
    }}
    request = Request(f"https://graph.facebook.com/{version}/{phone_id}/messages",
        data=json.dumps(payload).encode("utf-8"), headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8") or "{}")
            message_id = ((data.get("messages") or [{}])[0]).get("id")
            if 200 <= response.status < 300 and message_id:
                return True, f"aceito pelo WhatsApp para processamento (id {message_id})"
            return False, "O WhatsApp não confirmou que aceitou a mensagem"
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as error:
        return False, _provider_error(error)


def send_code(channel, destination, code):
    message = f"Seu código de confirmação do Ponto de Coleta Adelinha é {code}. Ele expira em 10 minutos."
    if channel == "email":
        return send_email(destination, "Código de confirmação", message)
    if channel == "whatsapp":
        return _send_whatsapp(destination, code)
    return False, "Canal inválido"
