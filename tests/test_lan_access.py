"""局域网登录码、签名会话与私网 Host 边界测试。"""
import json
import tempfile
import threading
import unittest
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from lan_auth import COOKIE, LanAuth
from security import local_boundary
from server import LibraryStore, make_handler
from test_practice import fixture


class HeaderBag:
    def __init__(self, host, origin=None, site='same-origin'):
        self.host = host
        self.origin = origin
        self.site = site

    def get_all(self, name, default=None):
        values = {'Host': self.host, 'Origin': self.origin, 'Sec-Fetch-Site': self.site}
        value = values.get(name)
        return [] if value is None else [value]

    def get(self, name, default=''):
        return {'Host': self.host, 'Origin': self.origin, 'Sec-Fetch-Site': self.site}.get(name) or default


def cookie_from_header(header):
    cookie = SimpleCookie()
    cookie.load(header)
    morsel = cookie.get(COOKIE)
    return '%s=%s' % (COOKIE, morsel.value)


class LanAuthTests(unittest.TestCase):
    def test_code_file_session_and_restart_behavior(self):
        with tempfile.TemporaryDirectory() as temp:
            auth = LanAuth(temp)
            self.assertTrue(auth.verify_code(auth.code))
            self.assertFalse(auth.verify_code('wrong-code'))
            self.assertEqual(auth.code_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(auth.auth_file.stat().st_mode & 0o777, 0o600)
            cookie = cookie_from_header(auth.cookie_header())
            self.assertTrue(auth.valid_cookie(cookie))
            renewed = LanAuth(temp)
            self.assertNotEqual(renewed.code, auth.code)
            self.assertTrue(renewed.valid_cookie(cookie), 'session secret should survive restart')
            renewed.rotate_secret()
            self.assertFalse(renewed.valid_cookie(cookie))

    def test_expired_or_tampered_cookie_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            auth = LanAuth(temp)
            auth.ttl = -1
            expired = cookie_from_header(auth.cookie_header())
            self.assertFalse(auth.valid_cookie(expired))
            auth.ttl = 3600
            valid = cookie_from_header(auth.cookie_header())
            self.assertFalse(auth.valid_cookie(valid + 'x'))


class LanBoundaryTests(unittest.TestCase):
    def test_private_and_loopback_hosts_are_allowed_only_in_lan_mode(self):
        private = HeaderBag('10.25.48.100:8765')
        public = HeaderBag('8.8.8.8:8765')
        self.assertTrue(local_boundary(private, 8765, 'GET', '/', lan=True))
        self.assertFalse(local_boundary(public, 8765, 'GET', '/', lan=True))
        self.assertFalse(local_boundary(private, 8765, 'GET', '/', lan=False))
        self.assertTrue(local_boundary(private, 8765, 'POST', '/api/session', lan=True))

    def test_foreign_origin_is_rejected(self):
        headers = HeaderBag('10.25.48.100:8765', 'http://evil.example')
        self.assertFalse(local_boundary(headers, 8765, 'POST', '/api/session', lan=True))


class LanHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'library.json'
        self.path.write_text(json.dumps(fixture(), ensure_ascii=False), encoding='utf-8')
        self.auth = LanAuth(self.root)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(
            LibraryStore(self.path), type('AI', (), {'lock': threading.Lock()})(), lan=True, auth=self.auth))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:%d' % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, path, method='GET', data=None, cookie=None):
        headers = {'Content-Type': 'application/json'} if data is not None else {}
        if cookie:
            headers['Cookie'] = cookie
        return urlopen(Request(self.base + path, data=data, headers=headers, method=method), timeout=10)

    def test_login_required_then_cookie_opens_library_and_logout_revokes(self):
        with self.request('/') as response:
            body = response.read().decode('utf-8')
        self.assertEqual(response.status, 200)
        self.assertIn('局域网登录', body)
        with self.assertRaises(Exception) as missing:
            self.request('/api/library')
        self.assertEqual(getattr(missing.exception, 'code', None), 401)
        with self.assertRaises(Exception) as wrong:
            self.request('/api/session', 'POST', json.dumps({'code': 'wrong'}).encode())
        self.assertEqual(getattr(wrong.exception, 'code', None), 401)
        with self.request('/api/session', 'POST', json.dumps({'code': self.auth.code}).encode()) as response:
            header = response.headers.get('Set-Cookie')
        self.assertTrue(header)
        cookie = cookie_from_header(header)
        with self.request('/api/library', cookie=cookie) as response:
            self.assertEqual(response.status, 200)
            data = json.load(response)
        self.assertEqual(data['schemaVersion'], 1)
        with self.request('/api/session/logout', 'POST', b'{}', cookie=cookie) as response:
            self.assertEqual(response.status, 200)
        with self.assertRaises(Exception) as expired:
            self.request('/api/library', cookie=cookie)
        self.assertEqual(getattr(expired.exception, 'code', None), 401)


if __name__ == '__main__':
    unittest.main()
