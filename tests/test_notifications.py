import json
from io import BytesIO
from urllib.error import HTTPError

import notifications


class FakeSMTP:
    instances = []
    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout, self.events = host, port, timeout, []
        self.__class__.instances.append(self)
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def ehlo(self): self.events.append("ehlo")
    def starttls(self): self.events.append("starttls")
    def login(self, user, password): self.events.append(("login", user, password))
    def send_message(self, message): self.message = message; return {}


def test_email_starttls_is_supported(monkeypatch):
    for name, value in {"SMTP_HOST":"smtp.test", "SMTP_PORT":"587", "SMTP_SECURITY":"starttls", "SMTP_USER":"user", "SMTP_PASSWORD":"secret", "SMTP_FROM":"no-reply@test.invalid"}.items():
        monkeypatch.setenv(name, value)
    FakeSMTP.instances.clear(); monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)
    ok, detail = notifications.send_code("email", "cliente@test.invalid", "123456")
    assert ok and "aceito" in detail
    instance = FakeSMTP.instances[-1]
    assert instance.port == 587 and "starttls" in instance.events
    assert "123456" in instance.message.get_content()


def test_email_missing_configuration_does_not_simulate_success(monkeypatch):
    for name in ("SMTP_HOST", "SMTP_FROM", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    ok, detail = notifications.send_code("email", "cliente@test.invalid", "123456")
    assert not ok and "não configurado" in detail


def test_whatsapp_uses_approved_template_and_brazil_e164(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "codigo_recuperacao")
    monkeypatch.setenv("WHATSAPP_GRAPH_VERSION", "v99.0")
    captured = {}
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self): return b'{"messages":[{"id":"wamid.1"}]}'
    def fake_open(request, timeout):
        captured.update(json.loads(request.data)); return Response()
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
