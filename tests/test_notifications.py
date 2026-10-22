import base64
import json
from email import message_from_bytes
from io import BytesIO
from urllib.error import HTTPError

import notifications


class Response:
    def __init__(self, body, status=200):
        self.body, self.status = body, status
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self): return json.dumps(self.body).encode()


def gmail_environment(monkeypatch):
    monkeypatch.setenv("GMAIL_CLIENT_ID", "client-id")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("GMAIL_SENDER", "pontodecoletaadelinha@gmail.com")


def test_gmail_refreshes_token_and_sends_encoded_message(monkeypatch):
    gmail_environment(monkeypatch)
    requests = []
    def fake_open(request, timeout):
        requests.append(request)
        if request.full_url.endswith("/token"):
            assert b"grant_type=refresh_token" in request.data
            assert b"refresh-token" in request.data
            return Response({"access_token": "short-lived-access-token", "expires_in": 3600})
        assert request.full_url.endswith("/gmail/v1/users/me/messages/send")
        assert request.headers["Authorization"] == "Bearer short-lived-access-token"
        payload = json.loads(request.data)
        raw = base64.urlsafe_b64decode(payload["raw"] + "==")
        email = message_from_bytes(raw)
        assert email["From"] == "Ponto de Coleta Adelinha <pontodecoletaadelinha@gmail.com>"
        assert email["Reply-To"] == "pontodecoletaadelinha@gmail.com"
        assert email["To"] == "cliente@example.com"
        assert "123456" in email.get_payload(decode=True).decode("utf-8")
        assert "Me Guarde" in email.get_payload(decode=True).decode("utf-8")
        assert "Comprou? Deixa com a gente." in email.get_payload(decode=True).decode("utf-8")
        return Response({"id": "gmail-message-1", "labelIds": ["SENT"]})
    monkeypatch.setattr(notifications, "urlopen", fake_open)
    ok, detail = notifications.send_code("email", "cliente@example.com", "123456")
    assert ok and "gmail-message-1" in detail
    assert len(requests) == 2


def test_gmail_missing_configuration_does_not_simulate_success(monkeypatch):
    for name in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    ok, detail = notifications.send_code("email", "cliente@example.com", "123456")
    assert not ok and "não configurado" in detail


def test_gmail_refresh_error_is_clear_and_does_not_send(monkeypatch):
    gmail_environment(monkeypatch)
    error = HTTPError("https://oauth2.googleapis.com/token", 400, "bad", {},
                      BytesIO(b'{"error":"invalid_grant","error_description":"Token has been expired or revoked"}'))
    monkeypatch.setattr(notifications, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    ok, detail = notifications.send_email("cliente@example.com", "Assunto", "Mensagem")
    assert not ok and "OAuth do Google" in detail and "invalid_grant" in detail


def test_whatsapp_uses_approved_template_and_brazil_e164(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "codigo_recuperacao")
    monkeypatch.setenv("WHATSAPP_GRAPH_VERSION", "v99.0")
    captured = {}
    def fake_open(request, timeout):
        captured.update(json.loads(request.data)); return Response({"messages": [{"id": "wamid.1"}]})
    monkeypatch.setattr(notifications, "urlopen", fake_open)
    ok, detail = notifications.send_code("whatsapp", "(16) 98800-4966", "654321")
    assert ok and "wamid.1" in detail
    assert captured["to"] == "5516988004966"
    assert captured["type"] == "template"
    assert captured["template"]["components"][0]["parameters"][0]["text"] == "654321"


def test_whatsapp_provider_error_is_reported(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "codigo_recuperacao")
    monkeypatch.setenv("WHATSAPP_GRAPH_VERSION", "v99.0")
    error = HTTPError("https://example.invalid", 400, "bad", {}, BytesIO(b'{"error":{"code":132001,"message":"Template not found"}}'))
    monkeypatch.setattr(notifications, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    ok, detail = notifications.send_code("whatsapp", "16988004966", "123456")
    assert not ok and "132001" in detail and "Template not found" in detail
