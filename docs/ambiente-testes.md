# Ambiente de testes separado

- Produção: www.pontodecoletaadelinha.com, main, porta local 8000,
  ponto-coleta.service, /etc/ponto-coleta/site.env.
- Testes: pontodecoletaadl.servehttp.com, develop, porta local 8001,
  ponto-coleta-teste.service, /etc/ponto-coleta/site-teste.env,
  /home/ubuntu/sistema-ponto-de-coleta-adelinha-teste.

O ambiente de testes usa o banco antigo preservado. Não copia credenciais da
produção. SITE_ENVIRONMENT=test bloqueia WhatsApp e chamadas reais à Fast,
mesmo com chaves inseridas indevidamente, e desativa login administrativo legado.
Google e Gmail permanecem bloqueados por padrão e exigem liberação explícita abaixo. O acesso de administrador usa a conta principal que já
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

Não trocar DATABASE_URL da produção para testar. Pagamentos reais permanecem
bloqueados. Testes automatizados usam provedores simulados.

## Google e Gmail separados

Criar clientes OAuth próprios para Login e Gmail de testes. Preencher somente
/etc/ponto-coleta/site-teste.env, sem copiar credenciais da produção:

```ini
STAGING_GOOGLE_LOGIN_ENABLED=1
GOOGLE_LOGIN_ENABLED=1
GOOGLE_LOGIN_CLIENT_ID=<cliente Login Testes>
GOOGLE_LOGIN_CLIENT_SECRET=<segredo Login Testes>
GOOGLE_LOGIN_REDIRECT_URI=https://pontodecoletaadl.servehttp.com/cliente/google/retorno
STAGING_EMAIL_ENABLED=1
STAGING_EMAIL_RECIPIENTS=<endereços de teste separados por vírgula>
GMAIL_CLIENT_ID=<cliente Gmail Testes>
GMAIL_CLIENT_SECRET=<segredo Gmail Testes>
GMAIL_REFRESH_TOKEN=<token autorizado por pontodecoletaadelinha@gmail.com>
```

Remetente permanece pontodecoletaadelinha@gmail.com. Os envios são reais, com
assunto [TESTES], e só permitem destinatários explicitamente listados. Lista vazia
bloqueia Gmail inclusive a renovação de token; destinatários fora da lista não
fazem chamadas externas. Não há redirecionamento silencioso de códigos pessoais.
Não instalar timers de notificações para o ambiente de testes.
Após atualizar o código, reiniciar somente ponto-coleta-teste.service.
Para desativar, definir STAGING_EMAIL_ENABLED=0 e/ou
STAGING_GOOGLE_LOGIN_ENABLED=0 e reiniciar esse serviço. Produção não usa essas
opções. O retorno Google em testes deve ser exatamente o domínio antigo acima.
