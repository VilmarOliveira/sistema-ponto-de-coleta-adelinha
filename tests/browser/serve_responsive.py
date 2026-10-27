"""Servidor de testes visuais local, com dados fictícios e integrações desativadas.

Não importa nem altera bancos configurados no ambiente. Execute na raiz do projeto.
"""
import io
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from flask import flash, render_template
from PIL import Image
from werkzeug.security import generate_password_hash
import app as application
from app import DatabaseConnection, create_app
from branding import DEFAULT_THEME
from test_app import signature
from test_customization import csrf, legacy_login

TEMPORARY = tempfile.TemporaryDirectory(prefix='adelinha-responsive-')
PASSWORD = 'responsivo-local-123'
application.send_code = lambda *args, **kwargs: (False, 'Envio desativado no servidor de testes visuais')
app = create_app({'TESTING': True, 'DATABASE': str(Path(TEMPORARY.name) / 'fixture.db'),
    'SECRET_KEY': 'somente-testes-visuais-locais', 'STAFF_USER': 'admin',
    'STAFF_PASSWORD_HASH': generate_password_hash(PASSWORD),
    'STAFF_NAME': 'Administrador de Testes com Nome Extenso para Verificar o Menu'})
client = app.test_client()
LONG_NAME = 'Cliente Responsividade ' + 'SobrenomeExtenso' * 8
ADDRESS = {'residential_cep': '14400000', 'residential_street': 'Rua de Teste com Nome Comprido ' * 4,
    'residential_number': '123', 'residential_district': 'Bairro Responsividade',
    'residential_city': 'Franca', 'residential_state': 'SP', 'residential_complement': 'Complemento de teste ' * 5}


def registration(name, cpf, email):
    response = client.post('/cadastro', data={'name': name, 'cpf': cpf, 'phone': '16999999999', 'email': email,
        'signature': signature(), 'password': PASSWORD, 'password_confirm': PASSWORD,
        'terms_accept': 'yes', **ADDRESS, 'csrf_token': csrf(client)})
    assert response.status_code == 200


def seed_fixtures():
    global blog_id
    registration(LONG_NAME, '52998224725', 'cliente-responsividade@example.test')
    registration('Cliente sem pacotes', '98765432100', 'cliente-vazio@example.test')
    legacy_login(client)
    for role in ('administrador', 'gerente', 'atendente'):
        response = client.post('/painel/configuracoes/usuarios', data={
            'name': role.title() + ' de Testes com Sobrenome Extenso', 'email': role + '@example.test',
            'password': PASSWORD, 'password_confirm': PASSWORD, 'role': role,
            'can_clients': 'yes', 'can_packages': 'yes', 'can_pickups': 'yes', 'csrf_token': csrf(client)})
        assert response.status_code == 302
    for index in (1, 2, 3):
        client.post('/pacotes', data={'client_id': 1, 'tracking': f'RESPONSIVIDADE{index}', 'shelf': 'PRATELEIRA123',
            'width': 10, 'height': 10, 'length': 10, 'weight': 1, 'csrf_token': csrf(client)})
        if index > 1:
            client.post(f'/pacotes/{index}/avisar', data={'csrf_token': csrf(client)})
    client.post('/retiradas', data={'package_ids': '3', 'receiver_name': LONG_NAME,
        'receiver_document': '52998224725', 'document_type': 'CPF', 'payment_method': 'Pix',
        'payment_confirmed': 'yes', 'pickup_signature': signature(), 'csrf_token': csrf(client)})
    image = io.BytesIO()
    Image.new('RGB', (2048, 684), '#00ced1').save(image, 'PNG')
    for position in (2, 3):
        client.post('/painel/configuracoes/banners', data={'position': str(position), 'active': 'yes',
            'alt_text': f'Imagem de teste {position}', 'image': (io.BytesIO(image.getvalue()), 'teste.png'), 'csrf_token': csrf(client)})
    client.post('/painel/configuracoes/fotos', data={'kind': 'Fachada', 'alt_text': 'Foto fictícia',
        'position': '1', 'image': (io.BytesIO(image.getvalue()), 'foto.png'), 'csrf_token': csrf(client)})
    client.post('/painel/configuracoes/aparencia', data={'name': 'Tema de Testes', **DEFAULT_THEME, 'csrf_token': csrf(client)})
    client.post('/painel/configuracoes/aparencia', data={'action': 'restore', 'csrf_token': csrf(client)})
    client.post('/painel/blog', data={'title': 'Título de artigo longo para testar responsividade em todas as telas ' * 2,
        'slug': 'responsividade-com-textos-longos', 'summary': 'Resumo com palavraslongas' * 12,
        'body': '## Teste de leitura\n\n' + ('EndereçoMuitoExtensoSemEspaços' * 12) + '\n\n- Primeiro item\n- Segundo item',
        'action': 'publish', 'cover_image': (io.BytesIO(image.getvalue()), 'capa.png'), 'csrf_token': csrf(client)})
    db = DatabaseConnection(app.config['DATABASE'])
    blog_id = db.execute("SELECT id FROM blog_posts WHERE slug='responsividade-com-textos-longos'").fetchone()['id']
    now = datetime.now(timezone.utc).isoformat()
    db.execute('''INSERT INTO verification_codes(client_id,purpose,channel,destination,code_hash,expires_at,provider_status,created_at)
        VALUES(?,?,?,?,?,?,?,?)''', (1, 'contract', 'email', 'teste@example.test', 'fake-hash', now,
        'Mensagem fictícia de provedor com informação técnica longa ' * 12, now))
    db.commit()
    db.close()



@app.get('/__responsive/case/<case>')
def visual_case(case):
    # Casos visuais com templates de produção, disponíveis só neste servidor local.
    if case == 'registration-error':
        flash('Confira os dados do cadastro e a mensagem de validação de cada campo. ' * 5, 'error')
        return render_template('index.html', registration_form={'name': LONG_NAME, 'cpf': '11111111111',
            'email': 'email-invalido', **ADDRESS}, show_registration=True, banners=[], photos=[])
    if case == 'success':
        return render_template('success.html', name=LONG_NAME, public_id='CLIPCA-123456789', address=application.ADDRESS)
    if case == 'password-link':
        return render_template('password_link.html', link='http://127.0.0.1:5001/definir-senha/' + 'tokenficticio' * 20, expires=datetime.now(timezone.utc).isoformat())
    if case in ('client-recovery-confirm', 'staff-recovery-confirm'):
        return render_template('password_recovery.html' if case.startswith('client') else 'staff_password_recovery.html',
            stage='confirm', masked_contact='cl***@example.test', recovery_email='administrador@example.test')
    if case == 'set-password':
        return render_template('set_password.html', invalid=False)
    if case == 'empty-blog':
        return render_template('blog.html', posts=[])
    return 'Caso visual não encontrado', 404


@app.get('/__responsive/manifest')
def manifest():
    return {'public': ['/', '/condicoes', '/login', '/cliente/login', '/cliente/recuperar-senha',
        '/equipe/recuperar-senha', '/duvidas-frequentes', '/blog', '/blog/responsividade-com-textos-longos',
        '/definir-senha/token-invalido', *['/__responsive/case/' + case for case in
        ('registration-error', 'success', 'client-recovery-confirm', 'staff-recovery-confirm', 'set-password', 'empty-blog')]],
        'admin': ['/painel', '/painel/clientes/1', '/painel/clientes/2', '/painel/pacotes/1',
        '/painel/pacotes/1/editar', '/painel/pacotes/1/excluir', '/painel/pacotes/3?retirada=sucesso',
        '/painel/metricas', '/painel/configuracoes', '/painel/configuracoes/identidade',
        '/painel/configuracoes/banners', '/painel/configuracoes/fotos', '/painel/configuracoes/aparencia',
        '/painel/configuracoes/aparencia?edit=1', '/painel/configuracoes/pix', '/painel/configuracoes/pix?editar=1',
        '/painel/configuracoes/usuarios?tab=clientes', '/painel/configuracoes/usuarios?tab=equipe',
        '/painel/configuracoes/usuarios?q_clients=SemResultados',
        '/painel/configuracoes/usuarios?tab=equipe&q_team=SemResultados', '/painel/configuracoes/notificacoes',
        '/painel/blog', f'/painel/blog?edit={blog_id}', '/__responsive/case/password-link'],
        'client': ['/cliente', '/cliente/editar', '/cliente/condicoes-aceitas', '/cliente/pacotes/2',
        '/cliente/pacotes/3', '/cliente/comprovantes/1'],
        'client_empty': ['/cliente'], 'manager': ['/painel', '/painel/clientes/1', '/painel/pacotes/3'],
        'clerk': ['/painel', '/painel/clientes/1', '/painel/pacotes/3']}


seed_fixtures()

if __name__ == '__main__':
    print('Servidor visual: banco temporário isolado, credenciais fictícias, nenhum e-mail real.')
    app.run(host='127.0.0.1', port=5001, use_reloader=False)
