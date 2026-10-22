import json
from pathlib import Path

import pytest

from scripts import authorize_gmail


def test_authorizer_requests_only_gmail_send():
    assert authorize_gmail.SCOPE == "https://www.googleapis.com/auth/gmail.send"
    assert authorize_gmail.SENDER == "pontodecoletaadelinha@gmail.com"


def test_authorizer_accepts_only_desktop_credentials(tmp_path):
    desktop = tmp_path / "credentials.json"
    desktop.write_text(json.dumps({"installed": {"client_id": "id", "client_secret": "secret"}}), encoding="utf-8")
    assert authorize_gmail.load_client(desktop)["client_id"] == "id"
    web = tmp_path / "web.json"
    web.write_text(json.dumps({"web": {"client_id": "id", "client_secret": "secret"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="App para computador"):
        authorize_gmail.load_client(web)
