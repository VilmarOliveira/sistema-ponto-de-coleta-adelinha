"""Switch only the former hostname to staging, preserving payment webhooks."""
import argparse
from datetime import datetime
import http.client
import os
import shlex
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]


def write_atomic(path,data,mode):
    fd,temp=tempfile.mkstemp(prefix='.test-proxy-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as file:
            os.fchmod(file.fileno(),mode);file.write(data);file.flush();os.fsync(file.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def check_production_origin(path='/etc/ponto-coleta/site.env'):
    values=[line.partition('=')[2].strip() for line in Path(path).read_text().splitlines()
            if line.partition('=')[0].strip()=='SITE_PUBLIC_ORIGIN']
    try:
        parts=shlex.split(values[0]) if len(values)==1 else []
    except ValueError:
        parts=[]
    if len(parts)!=1 or parts[0].rstrip('/')!='https://www.pontodecoletaadelinha.com':
        raise RuntimeError('Configure SITE_PUBLIC_ORIGIN=https://www.pontodecoletaadelinha.com no arquivo ativo e reinicie a produção antes de liberar os testes.')


def check_upstreams():
    subprocess.run(['systemctl','is-active','--quiet','ponto-coleta-teste.service'],check=True)
    with urlopen('http://127.0.0.1:8001/health',timeout=10) as response:
        if response.status!=200 or response.headers.get('X-Site-Environment')!='test':
            raise RuntimeError('A porta de testes não está identificada como teste.')
    with urlopen('http://127.0.0.1:8000/health',timeout=10) as response:
        if response.status!=200:raise RuntimeError('Confira a produção antes de alterar o proxy.')


def password_status():
    # New connection per attempt: retiring Nginx workers may still use the old vhost.
    connection=http.client.HTTPSConnection('127.0.0.1',443,context=ssl._create_unverified_context(),timeout=2)
    try:
        connection.request('GET','/health',headers={'Host':'pontodecoletaadl.servehttp.com','Connection':'close'})
        return connection.getresponse().status
    finally:
        connection.close()


def wait_for_password(probe=None, *, attempts=20, delay=.25):
    probe=probe or password_status
    last='sem resposta'
    for attempt in range(attempts):
        try:
            status=probe()
            last='HTTP '+str(status)
            if status==401:return
        except (OSError,http.client.HTTPException):
            last='sem resposta'
        if attempt+1<attempts:time.sleep(delay)
    raise RuntimeError('Proteção por senha não confirmada após aguardar a recarga (último resultado: '+last+').')


def activate(config,template,backup_folder):
    config=Path(config).resolve();template=Path(template)
    before=config.read_bytes()
    if b'pontodecoletaadl.servehttp.com' not in before or b'pontodecoletaadelinha.com' in before:
        raise RuntimeError('Arquivo contém outro domínio ou não é a configuração antiga. Nenhuma troca feita.')
    check_production_origin()
    check_upstreams()
    if not Path('/etc/nginx/.htpasswd-ponto-coleta-teste').is_file():
        raise RuntimeError('Crie primeiro a senha de acesso ao ambiente de testes.')
    backup_folder=Path(backup_folder);backup_folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    backup=backup_folder/('nginx-antes-teste-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.conf')
    fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as file:file.write(before)
    phase='gravação da configuração de testes'
    try:
        write_atomic(config,template.read_bytes(),config.stat().st_mode & 0o777)
        phase='validação nginx -t'
        subprocess.run(['nginx','-t'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        phase='recarregamento do Nginx'
        subprocess.run(['systemctl','reload','nginx'],check=True)
        phase='confirmação da proteção por senha'
        wait_for_password()
        phase='saúde dos serviços após a recarga'
        check_upstreams()
    except Exception as error:
        reason=str(error) if isinstance(error,RuntimeError) else 'Falha na etapa: '+phase+'.'
        try:
            write_atomic(config,before,config.stat().st_mode & 0o777)
            subprocess.run(['nginx','-t'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            subprocess.run(['systemctl','reload','nginx'],check=True)
        except Exception:
            raise RuntimeError('Ativação falhou e restauração não foi confirmada. Backup: '+str(backup)+'. '+reason) from None
        raise RuntimeError('Ativação não concluída; configuração anterior do Nginx restaurada. Motivo: '+reason) from None
    return backup


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='/etc/nginx/sites-enabled/ponto-coleta')
    parser.add_argument('--template',default=str(ROOT/'deployment/nginx/ponto-coleta-teste.conf'))
    parser.add_argument('--backup-folder',default='/var/backups/ponto-coleta')
    args=parser.parse_args(argv)
    try:
        backup=activate(args.config,args.template,args.backup_folder)
        print('Proxy de testes ativado. Backup do Nginx:',backup)
        print('Webhooks antigos continuam na produção. O domínio www não foi alterado.')
        return 0
    except Exception as error:
        if isinstance(error,RuntimeError):print(str(error),file=sys.stderr)
        else:print('Confira serviço de testes, certificado, senha e configuração do Nginx.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
