"""Autoriza uma conta Gmail localmente e gera as variáveis para o Render."""
import argparse
import json
import os
import secrets
import stat
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

SCOPE = "https://www.googleapis.com/auth/gmail.send"
SENDER = "vilmar920@gmail.com"


def load_client(path):
    content = json.loads(Path(path).read_text(encoding="utf-8"))
    client = content.get("installed")
    if not client or not client.get("client_id") or not client.get("client_secret"):
        raise ValueError("O JSON precisa ser uma credencial OAuth do tipo App para computador.")
    return client


def authorize(client):
    state = secrets.token_urlsafe(32)
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            values = parse_qs(urlparse(self.path).query)
            if values.get("state", [None])[0] != state:
                self.send_response(400); self.end_headers(); self.wfile.write(b"Estado invalido."); return
            result["code"] = values.get("code", [None])[0]
            result["error"] = values.get("error", [None])[0]
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write("<h1>Autorizacao concluida</h1><p>Volte ao terminal. Esta janela pode ser fechada.</p>".encode("utf-8"))
        def log_message(self, *_args):
            return

    server = HTTPServer(("127.0.0.1", 0), Callback)
    server.timeout = 300
    redirect_uri = f"http://127.0.0.1:{server.server_port}/"
    query = urlencode({"client_id": client["client_id"], "redirect_uri": redirect_uri,
        "response_type": "code", "scope": SCOPE, "access_type": "offline", "prompt": "consent",
        "state": state, "include_granted_scopes": "false", "login_hint": SENDER})
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + query
    print("Abrindo o navegador para autorizar somente gmail.send...")
    if not webbrowser.open(url):
        print("Abra manualmente este endereço no navegador:\n" + url)
    server.handle_request(); server.server_close()
    if result.get("error"):
        raise RuntimeError(f"Autorização recusada pelo Google: {result['error']}")
    if not result.get("code"):
        raise RuntimeError("A autorização não foi concluída dentro de 5 minutos.")
    request = Request("https://oauth2.googleapis.com/token", data=urlencode({"code": result["code"],
        "client_id": client["client_id"], "client_secret": client["client_secret"],
        "redirect_uri": redirect_uri, "grant_type": "authorization_code"}).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(request, timeout=30) as response:
        tokens = json.loads(response.read().decode("utf-8"))
    if not tokens.get("refresh_token"):
        raise RuntimeError("O Google não retornou Refresh Token. Revogue o acesso anterior e execute novamente.")
    granted = set((tokens.get("scope") or "").split())
    if granted != {SCOPE}:
        raise RuntimeError("O Google retornou escopos diferentes de gmail.send; nada foi salvo.")
    return tokens["refresh_token"]


def main():
    parser = argparse.ArgumentParser(description="Gera autorização Gmail para configurar no Render sem enviar e-mail.")
    parser.add_argument("credentials", help="Caminho do JSON OAuth do tipo App para computador")
    parser.add_argument("--output", default="gmail-render.env", help="Arquivo local de saída (padrão: gmail-render.env)")
    args = parser.parse_args()
    try:
        client = load_client(args.credentials)
        refresh_token = authorize(client)
        output = Path(args.output).resolve()
        output.write_text("\n".join((f"GMAIL_CLIENT_ID={client['client_id']}",
            f"GMAIL_CLIENT_SECRET={client['client_secret']}", f"GMAIL_REFRESH_TOKEN={refresh_token}",
            f"GMAIL_SENDER={SENDER}", "")), encoding="utf-8")
        try: output.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError: pass
        print(f"Autorização salva em: {output}")
        print("Esse arquivo contém segredos. Não o envie ao GitHub nem compartilhe seu conteúdo.")
        print("Nenhum e-mail foi enviado.")
    except (OSError, ValueError, RuntimeError, HTTPError, URLError, json.JSONDecodeError) as error:
        print(f"ERRO: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
