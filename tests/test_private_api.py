"""No real credentials or paid calls: private HTTPS boundary and direct API flow."""
import http.client
import io
import json
import tempfile
import threading
import unittest
from email.message import Message
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from deepseek_api import list_models
from integrations import IntegrationError, Integrations
from private_server import PrivateAuth, PrivateIntegrations, https_boundary, public_origin
from server import LibraryStore, make_handler
from test_practice import fixture

PASSWORD = 'test-only-secret-passphrase-0123456789'
ORIGIN = 'https://atlas.example.test'


def cookie_value(header):
    parsed = SimpleCookie(); parsed.load(header)
    return '; '.join('%s=%s' % (key, value.value) for key, value in parsed.items())


class PrivateAuthTests(unittest.TestCase):
    def test_restart_password_change_logout_and_secure_cookie(self):
        with tempfile.TemporaryDirectory() as root:
            auth = PrivateAuth(root, PASSWORD); cookie = cookie_value(auth.cookie_header())
            self.assertTrue(auth.verify_code(PASSWORD)); self.assertFalse(auth.verify_code('wrong-password-000000'))
            self.assertIn('; Secure', auth.cookie_header()); self.assertIn('HttpOnly', auth.cookie_header())
            self.assertTrue(PrivateAuth(root, PASSWORD).valid_cookie(cookie))
            auth.rotate_secret(); self.assertFalse(auth.valid_cookie(cookie)); self.assertTrue(auth.verify_code(PASSWORD))
            new_cookie = cookie_value(auth.cookie_header())
            self.assertTrue(PrivateAuth(root, PASSWORD).valid_cookie(new_cookie))
            changed = PrivateAuth(root, PASSWORD + '-new')
            self.assertFalse(changed.valid_cookie(new_cookie)); self.assertTrue(changed.verify_code(PASSWORD + '-new'))
            text = auth.auth_file.read_text(); self.assertNotIn(PASSWORD, text)
            self.assertEqual(auth.auth_file.stat().st_mode & 0o777, 0o600)

    def test_fail_closed_without_https_or_strong_password(self):
        for origin in ['http://atlas.example.test', 'https://user:pw@atlas.test', 'https://*.test', 'https://atlas.test/path']:
            with self.assertRaises(ValueError): public_origin(origin)
        with tempfile.TemporaryDirectory() as root:
            for password in ['', '1234', 'replace-with-a-password']:
                with self.assertRaises(ValueError): PrivateAuth(root, password)
        policy = https_boundary(ORIGIN)
        headers = Message(); headers['Host'] = 'atlas.example.test'; headers['X-Forwarded-Proto'] = 'https'
        self.assertTrue(policy(headers, 'GET', '/'))
        headers['Origin'] = 'https://evil.test'; self.assertFalse(policy(headers, 'POST', '/api/session'))
        del headers['Origin']; headers['Host'] = 'evil.test'; self.assertFalse(policy(headers, 'GET', '/api/library'))
        del headers['Host']; headers['Host'] = 'atlas.example.test'
        del headers['X-Forwarded-Proto']; self.assertFalse(policy(headers, 'GET', '/'))


class DirectAPITests(unittest.TestCase):
    def test_model_check_uses_official_host_without_persisting_draft_or_using_harness(self):
        with tempfile.TemporaryDirectory() as root:
            engine = Integrations(root)
            raw = io.BytesIO(json.dumps({'data': [{'id': 'account-model'}]}).encode())
            with patch('deepseek_api.credential_urlopen', return_value=raw) as call, patch.object(engine, 'rpc', side_effect=AssertionError('Harness must not be used')):
                result = list_models(engine, 'test-only-api-key')
            self.assertEqual(call.call_args.args[0].full_url, 'https://api.deepseek.com/models')
            self.assertEqual(result['models'], [{'id': 'account-model'}]); self.assertNotIn('apiKey', json.dumps(result))
            self.assertFalse((engine.local/'ai.json').exists())

    def test_summary_calls_deepseek_directly_and_does_not_return_api_key(self):
        with tempfile.TemporaryDirectory() as root:
            engine = PrivateIntegrations(root)
            engine.save_ai({'mode': 'deepseek', 'model': 'account-model', 'apiKey': 'test-only-api-key'})
            response = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'notes': 'IP enables network addressing. [S1]', 'cornell': {'cues': ['What does IP do?'], 'summary': 'IP enables network addressing. [S1]'}})}}], 'model': 'account-model'}
            data = fixture()
            with patch('integrations.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as call, patch.object(engine, 'rpc', side_effect=AssertionError('Harness must not be used')):
                result = engine.generate({'mode': 'summary', 'videoIds': ['v1']}, data)
            self.assertEqual(call.call_args.args[0].full_url, 'https://api.deepseek.com/chat/completions')
            body = json.loads(call.call_args.args[0].data); self.assertEqual(body['model'], 'account-model')
            self.assertNotIn('test-only-api-key', json.dumps(result)); self.assertEqual(engine.read('harness'), {})

    def test_private_server_rejects_local_modes_and_invalid_model(self):
        with tempfile.TemporaryDirectory() as root:
            engine = PrivateIntegrations(root)
            self.assertEqual(engine.read('ai')['mode'], 'deepseek')
            for data in [{'mode': 'harness'}, {'mode': 'compatible', 'compatible': {'provider': 'ollama'}}, {'mode': 'deepseek', 'model': 'bad model'}]:
                with self.assertRaises(IntegrationError): engine.save_ai(data)


class PrivateHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        path = root/'library.json'; path.write_text(json.dumps(fixture()))
        self.ai = PrivateIntegrations(root); self.auth = PrivateAuth(root, PASSWORD)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(LibraryStore(path), self.ai, lan=True, auth=self.auth, access_policy=https_boundary(ORIGIN)))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.tmp.cleanup()
    def request(self, path, data=None, cookie=None, token=None, extra=None):
        headers={'Content-Type': 'application/json', 'Host': 'atlas.example.test', 'X-Forwarded-Proto': 'https', 'Origin': ORIGIN}
        if cookie: headers['Cookie'] = cookie
        if token: headers['X-Study-Atlas-Token'] = token
        headers.update(extra or {})
        body=json.dumps(data).encode() if data is not None else None
        conn=http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request('POST' if data is not None else 'GET',path,body=body,headers=headers)
        response=conn.getresponse(); result=(response.status,dict(response.getheaders()),response.read());conn.close();return result
    def test_login_settings_model_metadata_and_logout_preserve_boundaries(self):
        self.assertEqual(self.request('/api/library')[0],401)
        self.assertEqual(self.request('/api/session/logout', {})[0],401)
        status, headers, _ = self.request('/api/session', {'code': PASSWORD})
        self.assertEqual(status,200); self.assertIn('Secure',headers['Set-Cookie']); cookie=cookie_value(headers['Set-Cookie'])
        self.assertEqual(self.request('/api/library',cookie=cookie)[0],200)
        token=json.loads(self.request('/api/security',cookie=cookie)[2])['token']
        self.assertEqual(self.request('/api/integrations/ai',{'mode':'deepseek'},cookie=cookie)[0],403)
        status, _, body=self.request('/api/integrations/ai',{'mode':'deepseek','model':'account-model','apiKey':'test-only-api-key'},cookie=cookie,token=token)
        self.assertEqual(status,200);self.assertNotIn(b'test-only-api-key',body)
        with patch('deepseek_api.credential_urlopen',return_value=io.BytesIO(b'{"data":[{"id":"account-model"}]}')):
            self.assertEqual(self.request('/api/integrations/deepseek/models',{},cookie=cookie,token=token)[0],200)
        self.assertEqual(self.request('/api/library',cookie=cookie,extra={'Origin':'https://evil.test'})[0],403)
        self.assertEqual(self.request('/api/session/logout',{},cookie=cookie)[0],200)
        self.assertEqual(self.request('/api/library',cookie=cookie)[0],401)
