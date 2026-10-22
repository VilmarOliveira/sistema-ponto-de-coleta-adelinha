import io
import json
import sqlite3

from PIL import Image
from werkzeug.security import generate_password_hash

from app import create_app


def csrf(client):
    with client.session_transaction() as session:
        session.setdefault("csrf_token", "customization-csrf")
        return session["csrf_token"]


def legacy_login(client):
    with client.session_transaction() as session:
        session["staff"] = "staff"
        session["staff_legacy"] = True
        session["csrf_token"] = "customization-csrf"


def test_me_guarde_home_support_and_email_only_recovery(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": str(tmp_path / "app.db")})
    client = app.test_client()
    home = client.get("/").text
    hero = home.split('<section class="hero">', 1)[1].split("</section>", 1)[0]
    assert "ME GUARDE" in hero and "COMPROU? DEIXA COM A GENTE." in hero
    assert "PONTO DE COLETA ADELINHA" not in hero.upper()
    assert 'aria-label="Fale com a gente pelo WhatsApp"' in home
    assert "wa.me/5516988004966" in home
    recovery = client.get("/cliente/recuperar-senha").text
    assert "exclusivamente ao e-mail" in recovery
    assert 'name="channel"' not in recovery
    rejected = client.post("/cliente/recuperar-senha", data={"stage": "request", "cpf": "52998224725", "channel": "whatsapp", "csrf_token": csrf(client)})
    assert rejected.status_code == 400


def test_banner_upload_home_display_and_persistence(tmp_path):
    database = str(tmp_path / "app.db")
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": database})
    client = app.test_client(); legacy_login(client)
    output = io.BytesIO()
    Image.new("RGB", (24, 24), "orange").save(output, "WEBP")
    image = output.getvalue()
    response = client.post("/painel/configuracoes/banners", data={
        "position": "1", "alt_text": "Cliente recebendo uma encomenda",
        "image": (io.BytesIO(image), "banner.webp"), "csrf_token": csrf(client),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200 and "Banner salvo" in response.text
    home = client.get("/").text
    assert "Cliente recebendo uma encomenda" in home and "data-carousel" in home
    assert client.get("/banners/1/imagem").data == image
    restarted = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": database}).test_client()
    assert restarted.get("/banners/1/imagem").data == image


def test_theme_persists_and_staff_permissions_are_enforced(tmp_path):
    database = str(tmp_path / "app.db")
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": database})
    client = app.test_client(); legacy_login(client)
    colors = {"primary":"#cc3300","secondary":"#442277","page":"#ffffff","surface":"#ffffff",
              "text":"#111111","link":"#442277","border":"#cccccc","header":"#ffffff",
              "footer":"#111111","button":"#cc3300","button_hover":"#992200"}
    result = client.post("/painel/configuracoes/aparencia", data={"name":"Campanha", **colors, "csrf_token":csrf(client)}, follow_redirects=True)
    assert "Tema salvo e ativado" in result.text
    assert "--orange:#cc3300" in client.get("/").text
    created = client.post("/painel/configuracoes/usuarios", data={
        "name":"Administrador Principal", "email":"principal@example.com", "password":"senha-segura",
        "role":"administrador", "is_primary":"yes", "csrf_token":csrf(client)}, follow_redirects=True)
    assert "Usuário criado" in created.text
    client.post("/painel/configuracoes/usuarios", data={
        "name":"Atendente Limitado", "email":"atendente@example.com", "password":"senha-segura",
        "role":"atendente", "can_clients":"yes", "csrf_token":csrf(client)})
    client.post("/sair", data={"csrf_token": csrf(client)})
    client.post("/login", data={"user":"atendente@example.com", "password":"senha-segura", "csrf_token":csrf(client)})
    assert client.get("/painel/configuracoes/aparencia").status_code == 403
    assert client.post("/painel/retirada/resumo", data={"package_ids":"1", "csrf_token":csrf(client)}).status_code == 403
    restarted = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": database}).test_client()
    assert "--orange:#cc3300" in restarted.get("/").text
