"""Switch only the former hostname to staging, preserving payment webhooks."""
import argparse
from datetime import datetime
import http.client
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
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


def check_upstreams():
    subprocess.run(['systemctl','is-active','--quiet','ponto-coleta-teste.service'],check=True)
    with urlopen('http://127.0.0.1:8001/health',timeout=10) as response:
        if response.status!=200 or response.headers.get('X-Site-Environment')!='test':
            raise RuntimeError('A porta de testes não está identificada como teste.')
    with urlopen('http://127.0.0.1:8000/health',timeout=10) as response:
        if response.status!=200:raise RuntimeError('Confira a produção antes de alterar o proxy.')


def activate(config,template,backup_folder):
    config=Path(config).resolve();template=Path(template)
    before=config.read_bytes()
    if b'pontodecoletaadl.servehttp.com' not in before or b'pontodecoletaadelinha.com' in before:
        raise RuntimeError('Arquivo contém outro domínio ou não é a configuração antiga. Nenhuma troca feita.')
    check_upstreams()
    if not Path('/etc/nginx/.htpasswd-ponto-coleta-teste').is_file():
        raise RuntimeError('Crie primeiro a senha de acesso ao ambiente de testes.')
    backup_folder=Path(backup_folder);backup_folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    backup=backup_folder/('nginx-antes-teste-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.conf')
    fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as file:file.write(before)
    try:
        write_atomic(config,template.read_bytes(),config.stat().st_mode & 0o777)
        subprocess.run(['nginx','-t'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        subprocess.run(['systemctl','reload','nginx'],check=True)
        connection=http.client.HTTPSConnection('127.0.0.1',443,context=ssl._create_unverified_context(),timeout=10)
        try:
            connection.request('GET','/',headers={'Host':'pontodecoletaadl.servehttp.com'})
            response=connection.getresponse();status=response.status;response.read()
        finally:connection.close()
        if status!=401:raise RuntimeError('A proteção por senha não foi confirmada.')
        check_upstreams()
    except Exception:
        write_atomic(config,before,config.stat().st_mode & 0o777)
        subprocess.run(['nginx','-t'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        subprocess.run(['systemctl','reload','nginx'],check=True)
        raise RuntimeError('Ativação não concluída; configuração anterior do Nginx restaurada.') from None
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
