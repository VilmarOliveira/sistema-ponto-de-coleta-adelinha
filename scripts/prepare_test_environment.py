"""Write a separate credential-free staging environment; never changes live files."""
import argparse
import os
from pathlib import Path
import secrets
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_clean_production import read_env, PreparationError
from environment_mode import database_fingerprint


def prepare(production, old_test, destination):
    production, old_test, destination = map(Path, (production, old_test, destination))
    if destination.exists() or destination.resolve() in {production.resolve(), old_test.resolve()}:
        raise PreparationError('Arquivo de destino já existe; nenhuma configuração foi substituída.')
    prod = read_env(production)['DATABASE_URL']
    test = read_env(old_test)['DATABASE_URL']
    if not test.startswith(('postgresql://', 'postgres://')):
        raise PreparationError('Use o banco Neon de testes.')
    if database_fingerprint(prod) == database_fingerprint(test):
        raise PreparationError('Banco de testes não pode ser o banco de produção.')
    values = {'SITE_ENVIRONMENT':'test', 'DATABASE_URL':test, 'SECRET_KEY':secrets.token_urlsafe(48),
        'STAGING_PRODUCTION_FINGERPRINT':database_fingerprint(prod), 'COOKIE_SECURE':'1',
        'SITE_PUBLIC_ORIGIN':'https://pontodecoletaadl.servehttp.com',
        'FAST_PIX_PUBLIC_ORIGIN':'https://pontodecoletaadl.servehttp.com',
        'FAST_PIX_ENABLED':'0', 'FAST_PIX_NEW_CHARGES_ENABLED':'0', 'FAST_PIX_API_KEY':'',
        'FAST_PIX_WEBHOOK_SECRET':'', 'GMAIL_CLIENT_ID':'', 'GMAIL_CLIENT_SECRET':'',
        'GMAIL_REFRESH_TOKEN':'', 'GOOGLE_LOGIN_ENABLED':'0', 'GOOGLE_LOGIN_CLIENT_ID':'',
        'GOOGLE_LOGIN_CLIENT_SECRET':'', 'GOOGLE_LOGIN_REDIRECT_URI':'',
        'WHATSAPP_ACCESS_TOKEN':'', 'WHATSAPP_PHONE_NUMBER_ID':'',
        'WHATSAPP_TEMPLATE_NAME':'', 'WHATSAPP_GRAPH_VERSION':''}
    # Exclusive creation and mode 600 keep credentials off stdout and process args.
    fd = os.open(destination, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        for key,value in values.items():
            assert '\n' not in value and '\r' not in value
            stream.write(key+'="'+value.replace('\\','\\\\').replace('"','\\"')+'"\n')
    return destination


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production-env',default='/etc/ponto-coleta/site.env')
    parser.add_argument('--test-source-env',required=True)
    parser.add_argument('--output',default='/etc/ponto-coleta/site-teste.env')
    args=parser.parse_args(argv)
    try:
        file=prepare(args.production_env,args.test_source_env,args.output)
        print('Configuração de testes criada:',file)
        print('Produção não foi alterada. Credenciais de envio e pagamento não foram copiadas.')
        return 0
    except PreparationError as error:
        print(str(error),file=sys.stderr)
    except Exception:
        print('Configuração não concluída; confira os arquivos, sem compartilhar seus conteúdos.',file=sys.stderr)
    return 1


if __name__=='__main__':
    raise SystemExit(main())
