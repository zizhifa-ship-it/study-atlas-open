"""Local TLS reverse-proxy stand-in, private temporary state, fake cloud responses."""
import io
import json
import ssl
import subprocess
import sys
import tempfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from private_server import PrivateAuth, PrivateIntegrations, https_boundary
from server import LibraryStore, initialize_local_library, make_handler, ROOT
from test_knowledge import FakeKnowledgeAI

class CloudAI(PrivateIntegrations):
    def __init__(self, root):
        super().__init__(root); self.fake = FakeKnowledgeAI()
    def deepseek_generate(self, prompt): return self.fake.harness_generate(prompt)
    def harness_generate(self, prompt): raise AssertionError('No Harness allowed in this test')

with tempfile.TemporaryDirectory(prefix='atlas-private-browser-') as folder:
    root=Path(folder);(root/'data').mkdir()
    (root/'data/library.example.json').write_bytes((ROOT/'data/library.example.json').read_bytes())
    cert=root/'cert.pem';key=root/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=127.0.0.1'],check=True,capture_output=True)
    ThreadingHTTPServer.request_queue_size=64
    server=ThreadingHTTPServer(('127.0.0.1',0),None)
    origin='https://127.0.0.1:'+str(server.server_port)
    engine=CloudAI(root);auth=PrivateAuth(root,'test-only-private-password-123456')
    Base=make_handler(LibraryStore(initialize_local_library(root)),engine,lan=True,auth=auth,access_policy=https_boundary(origin))
    class TLSProxy(Base):
        def local_request(self):
            # Simulates the TLS proxy overwriting the client-supplied protocol header.
            del self.headers['X-Forwarded-Proto'];self.headers['X-Forwarded-Proto']='https'
            return super().local_request()
    server.RequestHandlerClass=TLSProxy
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
    server.socket=context.wrap_socket(server.socket,server_side=True,do_handshake_on_connect=False)
    def metadata(request, **kwargs):
        if request.full_url!='https://api.deepseek.com/models':raise AssertionError('Unexpected host')
        return io.BytesIO(b'{"data":[{"id":"account-model-a"},{"id":"account-model-b"}]}')
    with patch('deepseek_api.credential_urlopen',side_effect=metadata):
        print('TEST_URL='+origin,flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
