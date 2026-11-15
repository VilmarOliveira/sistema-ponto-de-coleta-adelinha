"""Real Nginx routing check with local fake backends and disposable certificates."""
import base64
from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import threading
import time
import pytest

TOOLS=all(shutil.which(x) for x in ['nginx','openssl','htpasswd'])


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]


class Backend(BaseHTTPRequestHandler):
    def handle_request(self):
        body=self.rfile.read(int(self.headers.get('Content-Length',0))).decode()
        value=json.dumps({'backend':self.server.label,'path':self.path,'method':self.command,'body':body}).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(value)));self.end_headers();self.wfile.write(value)
    do_GET=handle_request
    do_POST=handle_request
    def log_message(self,*a):pass


@pytest.mark.skipif(not TOOLS,reason='Nginx/OpenSSL/htpasswd disponíveis no job staging-routing')
def test_old_webhooks_remain_production_and_test_site_is_private(tmp_path):
    backends=[]; nginx=None
    try:
        for label in ['production','test']:
            server=ThreadingHTTPServer(('127.0.0.1',0),Backend);server.label=label
            threading.Thread(target=server.serve_forever,daemon=True).start();backends.append(server)
        production,test=[server.server_port for server in backends]
        http_port,https=port(),port()
        while https==http_port:https=port()
        crt,key,auth=[tmp_path/name for name in ['cert.pem','key.pem','auth']]
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(crt),'-days','1','-subj','/CN=localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(['htpasswd','-cb',str(auth),'fixture','fixture-password'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        template=(Path(__file__).resolve().parents[1]/'deployment/nginx/ponto-coleta-teste.conf').read_text()
        template=template.replace('listen 80;','listen 127.0.0.1:'+str(http_port)+';').replace('listen 443 ssl;','listen 127.0.0.1:'+str(https)+' ssl;')
        template=template.replace('http://127.0.0.1:8000','http://127.0.0.1:'+str(production)).replace('http://127.0.0.1:8001','http://127.0.0.1:'+str(test))
        template=template.replace('/etc/letsencrypt/live/pontodecoletaadl.servehttp.com/fullchain.pem',str(crt)).replace('/etc/letsencrypt/live/pontodecoletaadl.servehttp.com/privkey.pem',str(key)).replace('/etc/nginx/.htpasswd-ponto-coleta-teste',str(auth))
        template='\n'.join(line for line in template.splitlines() if 'options-ssl-nginx.conf' not in line and 'ssl_dhparam ' not in line)
        # The production vhost is independent and must remain public/unmodified.
        prod=f'''server {{ listen 127.0.0.1:{https} ssl; server_name www.pontodecoletaadelinha.com;
ssl_certificate {crt}; ssl_certificate_key {key}; location / {{ proxy_pass http://127.0.0.1:{production}; }} }}'''
        config=tmp_path/'nginx.conf'; config.write_text(f'pid {tmp_path}/nginx.pid; error_log {tmp_path}/error.log; events {{}} http {{ access_log off; {prod}\n{template}\n}}')
        subprocess.run(['nginx','-t','-c',str(config),'-p',str(tmp_path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        nginx=subprocess.Popen(['nginx','-c',str(config),'-p',str(tmp_path),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        def request(host,path='/',body=None,secure=True,authenticated=False):
            conn=(http.client.HTTPSConnection('127.0.0.1',https,context=ssl._create_unverified_context(),timeout=3)
                  if secure else http.client.HTTPConnection('127.0.0.1',http_port,timeout=3))
            headers={'Host':host}
            if authenticated:headers['Authorization']='Basic '+base64.b64encode(b'fixture:fixture-password').decode()
            conn.request('POST' if body is not None else 'GET',path,body=body,headers=headers)
            r=conn.getresponse();result=(r.status,dict(r.getheaders()),r.read());conn.close();return result
        for _ in range(50):
            try:
                with socket.create_connection(('127.0.0.1',https),timeout=.2):break
            except OSError:time.sleep(.1)
        host='pontodecoletaadl.servehttp.com'
        assert request(host)[0]==401
        status,headers,body=request(host,authenticated=True)
        assert status==200 and json.loads(body)['backend']=='test'
        assert 'noindex' in headers.get('X-Robots-Tag','')
        status,headers,_=request(host,secure=False)
        assert status==301 and headers['Location']=='https://pontodecoletaadl.servehttp.com/'
        for secure in [True,False]:
            for path in ['/webhooks/fastflow','/webhooks/fastflow/pedidos/old-order','/webhooks/fastflow/retiradas/old-order']:
                status,_,body=request(host,path,body='signed-fixture-body',secure=secure)
                payload=json.loads(body)
                assert status==200 and payload=={'backend':'production','path':path,'method':'POST','body':'signed-fixture-body'}
        assert json.loads(request('www.pontodecoletaadelinha.com')[2])['backend']=='production'
    finally:
        if nginx:
            nginx.terminate()
            try:nginx.communicate(timeout=5)
            except subprocess.TimeoutExpired:nginx.kill();nginx.communicate()
        for server in backends:server.shutdown();server.server_close()
