"""Integrações HTTPS de notificação sem simular sucesso de entrega."""
import base64
import json
import os
import re
from email.message import EmailMessage
from email.utils import formataddr
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_SENDER = "pontodecoletaadelinha@gmail.com"
GMAIL_DISPLAY_NAME = "Ponto de Coleta Adelinha"
EMAIL_SIGNATURE = "Me Guarde — Comprou? Deixa com a gente."


def notification_config_status():
    """Retorna o estado da configuração sem expor segredos."""
    email_ready = all((os.getenv("GMAIL_CLIENT_ID"), os.getenv("GMAIL_CLIENT_SECRET"),
                       os.getenv("GMAIL_REFRESH_TOKEN"))) and os.getenv("GMAIL_SENDER", GMAIL_SENDER).lower() == GMAIL_SENDER
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


def _json_http_error(error, provider):
    try:
        body = json.loads(error.read().decode("utf-8", errors="replace"))
        info = body.get("error", {})
        if isinstance(info, str):
            message, code = info, error.code
        else:
            message = str(info.get("message", "solicitação recusada"))[:240]
            code = info.get("code", error.code)
        return f"{provider} recusou a solicitação ({code}): {message}"
    except Exception:
        return f"{provider} recusou a solicitação (HTTP {error.code})"


def _gmail_access_token():
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")
    if not all((client_id, client_secret, refresh_token)):
        return None, "Gmail não configurado: confira Client ID, Client Secret e Refresh Token"
    request = Request("https://oauth2.googleapis.com/token", data=urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("ascii"), headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        token = result.get("access_token")
        if not token:
            return None, "O Google não retornou um token de acesso"
        return token, None
    except HTTPError as error:
        return None, _json_http_error(error, "OAuth do Google")
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        return None, "Não foi possível renovar a autorização do Gmail"


def send_email(destination, subject, body):
    """Envia pela Gmail API; sucesso significa aceitação pela API, não entrega."""
    sender = os.getenv("GMAIL_SENDER", GMAIL_SENDER).strip().lower()
    if sender != GMAIL_SENDER:
        return False, f"Remetente Gmail inválido; configure {GMAIL_SENDER}"
    access_token, error = _gmail_access_token()
    if not access_token:
        return False, error
    mail = EmailMessage()
    mail["From"] = formataddr((GMAIL_DISPLAY_NAME, GMAIL_SENDER))
    mail["Reply-To"], mail["To"], mail["Subject"] = GMAIL_SENDER, destination, subject
    mail.set_content(f"{body.rstrip()}\n\n{EMAIL_SIGNATURE}\n")
    raw = base64.urlsafe_b64encode(mail.as_bytes()).decode("ascii")
    request = Request("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=json.dumps({"raw": raw}).encode("utf-8"),
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8") or "{}")
        message_id = result.get("id")
        if 200 <= response.status < 300 and message_id:
            return True, f"aceito pela Gmail API para processamento (id {message_id})"
        return False, "A Gmail API não confirmou que aceitou a mensagem"
    except HTTPError as error:
        return False, _json_http_error(error, "Gmail API")
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        return False, "Não foi possível conectar à Gmail API"


def _provider_error(error):
    if isinstance(error, HTTPError):
        return _json_http_error(error, "WhatsApp")
    if isinstance(error, URLError):
        return "Não foi possível conectar ao serviço do WhatsApp"
    return f"Falha no provedor: {type(error).__name__}"


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
    payload = {"messaging_product": "whatsapp", "to": destination, "type": "template", "template": {
        "name": template_name, "language": {"code": os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "pt_BR")},
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
