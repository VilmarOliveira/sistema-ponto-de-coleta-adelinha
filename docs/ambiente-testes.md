# Ambiente de testes separado

- Produção: www.pontodecoletaadelinha.com, main, porta local 8000,
  ponto-coleta.service, /etc/ponto-coleta/site.env.
- Testes: pontodecoletaadl.servehttp.com, develop, porta local 8001,
  ponto-coleta-teste.service, /etc/ponto-coleta/site-teste.env,
  /home/ubuntu/sistema-ponto-de-coleta-adelinha-teste.

O ambiente de testes usa o banco antigo preservado. Não copia credenciais da
produção. SITE_ENVIRONMENT=test bloqueia Gmail, WhatsApp e chamadas reais à Fast,
mesmo com chaves inseridas indevidamente, e desativa Google OAuth e login
administrativo legado. O acesso de administrador usa a conta principal que já
existe no banco antigo, com seu e-mail e senha. O cookie e a chave de sessão são
separados. Não ativa Flask TESTING/debug. Uma impressão digital do banco de
produção impede inicializar os testes apontando para ele.

A faixa AMBIENTE DE TESTES identifica as telas. O proxy exige uma senha HTTP
adicional e adiciona noindex. Não instala timers de pagamentos ou e-mails para
testes. Webhooks antigos /webhooks/fastflow e seus caminhos de pedidos/retiradas
continuam encaminhados à produção, sem senha HTTP, preservando a validação HMAC
no aplicativo. O virtual host da produção não é modificado.

## Instalação guiada na Oracle

Primeiro mesclar a PR e preparar develop a partir da versão aprovada. Não
atualizar automaticamente a pasta de produção com commits ainda em testes.

1. Na pasta existente, git pull --ff-only origin main. Conferir no arquivo ativo
   SITE_PUBLIC_ORIGIN=https://www.pontodecoletaadelinha.com e reiniciar a produção
   após ajustar esse valor. Isso impede que lembretes de renovação levem usuários
   reais ao domínio de testes. A ativação do proxy recusa origem pública antiga.
2. Criar a configuração isolada, usando a cópia da configuração anterior à
   migração de banco, nunca o arquivo ativo como fonte dos dados de teste:

```bash
sudo .venv/bin/python scripts/prepare_test_environment.py --test-source-env /etc/ponto-coleta/site-teste-backup-20261114-161815.env
```

3. Clonar o mesmo repositório em outra pasta e criar um ambiente Python próprio:

```bash
git clone --branch develop --single-branch https://github.com/VilmarOliveira/sistema-ponto-de-coleta-adelinha.git /home/ubuntu/sistema-ponto-de-coleta-adelinha-teste
cd /home/ubuntu/sistema-ponto-de-coleta-adelinha-teste
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

4. Instalar a proteção HTTP (a senha é digitada no terminal, não em argumentos):

```bash
sudo apt-get update
sudo apt-get install -y apache2-utils
sudo htpasswd -cB /etc/nginx/.htpasswd-ponto-coleta-teste teste
sudo chown root:www-data /etc/nginx/.htpasswd-ponto-coleta-teste
sudo chmod 640 /etc/nginx/.htpasswd-ponto-coleta-teste
```

5. Instalar e iniciar somente o serviço de testes:

```bash
sudo install -m 644 deployment/systemd/ponto-coleta-teste.service /etc/systemd/system/ponto-coleta-teste.service
sudo systemctl daemon-reload
sudo systemctl enable --now ponto-coleta-teste.service
sudo systemctl is-active ponto-coleta-teste.service
```

Aguardar /health da porta 8001 responder 200 e X-Site-Environment: test. Conferir
que o serviço de produção permanece ativo antes de continuar.

6. Aplicar o proxy antigo por último:

```bash
sudo .venv/bin/python scripts/activate_test_proxy.py
```

O utilitário recusa arquivo contendo o domínio novo, verifica serviço, identidade
do ambiente, saúde da produção, existência da senha, testa nginx -t e confirma
HTTP 401 sem autenticação. Faz backup e restaura o Nginx se a validação falhar.
O certificado antigo é reutilizado; a validação HTTP do Certbot continua podendo
adicionar sua localização temporária fora da área protegida por senha.

## Atualizações futuras

Branch de alteração -> revisão/testes automatizados -> develop e atualização do
serviço de testes -> aprovação -> main e atualização da produção. Em testes:

```bash
cd /home/ubuntu/sistema-ponto-de-coleta-adelinha-teste
git pull --ff-only origin develop
.venv/bin/pip install -r requirements.txt
sudo systemctl restart ponto-coleta-teste.service
```

Não trocar DATABASE_URL da produção para testar. Fluxos manuais que exigem
entrega real de códigos ou pagamento real ficam desativados; testes automatizados
usam provedores simulados. Uma integração sandbox futura exige configuração
própria, sem reutilizar chaves de produção.
