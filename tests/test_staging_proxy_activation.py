"""File rollback guards without touching the host's Nginx or services."""
from pathlib import Path
import subprocess
import pytest
from scripts import activate_test_proxy as proxy


def test_production_vhost_is_refused_before_any_action(tmp_path,monkeypatch):
    config=tmp_path/'production.conf'; original=b'server_name www.pontodecoletaadelinha.com;'
    config.write_bytes(original)
    monkeypatch.setattr(proxy,'check_upstreams',lambda:pytest.fail('must not inspect services'))
    with pytest.raises(RuntimeError,match='outro domínio'):
        proxy.activate(config,tmp_path/'unused',tmp_path/'backups')
    assert config.read_bytes()==original and not (tmp_path/'backups').exists()


def test_invalid_nginx_configuration_restores_original_file(tmp_path,monkeypatch):
    config=tmp_path/'old.conf'; original=b'server_name pontodecoletaadl.servehttp.com; # original'
    config.write_bytes(original);template=tmp_path/'template.conf';template.write_bytes(b'invalid fixture configuration')
    monkeypatch.setattr(proxy,'check_upstreams',lambda:None)
    is_file=Path.is_file
    monkeypatch.setattr(Path,'is_file',lambda self:True if str(self)=='/etc/nginx/.htpasswd-ponto-coleta-teste' else is_file(self))
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        if len(calls)==1:raise subprocess.CalledProcessError(1,args)
    monkeypatch.setattr(proxy.subprocess,'run',run)
    with pytest.raises(RuntimeError,match='restaurada'):
        proxy.activate(config,template,tmp_path/'backups')
    assert config.read_bytes()==original
    backups=list((tmp_path/'backups').glob('*.conf'))
    assert len(backups)==1 and backups[0].read_bytes()==original
    assert backups[0].stat().st_mode & 0o777 == 0o600
    assert calls==[['nginx','-t'],['nginx','-t'],['systemctl','reload','nginx']]
