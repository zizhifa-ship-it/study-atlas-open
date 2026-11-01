"""可选的局域网访问：登录码 + 签名会话 Cookie，不开放公网。"""
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path

from security import private_fd_mode

COOKIE = 'studyatlas_session'
SESSION_TTL = 30 * 24 * 60 * 60


class LanAuth:
    def __init__(self, root, ttl=SESSION_TTL):
        self.local = Path(root) / '.local'
        self.local.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.auth_file = self.local / 'lan-auth.json'
        self.code_file = self.local / 'lan-code.txt'
        self.ttl = ttl
        self._load_or_create_secret()
        self.code = self._rotate_code()

    def _load_or_create_secret(self):
        data = {}
        try:
            data = json.loads(self.auth_file.read_text())
        except (OSError, ValueError):
            pass
        try:
            secret = bytes.fromhex(str(data.get('secret', '')))
            if len(secret) < 32:
                raise ValueError()
        except ValueError:
            secret = secrets.token_bytes(32)
        self.secret = secret
        self.created_at = data.get('createdAt') or datetime.now(timezone.utc).isoformat()

    def _private_write(self, path, text):
        fd, temporary = tempfile.mkstemp(dir=self.local, prefix='.lan-')
        try:
            private_fd_mode(fd)
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(text)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _rotate_code(self):
        code = secrets.token_urlsafe(9)
        salt = secrets.token_bytes(16)
        digest = hashlib.sha256(salt + code.encode()).hexdigest()
        data = {'version': 1, 'salt': salt.hex(), 'codeHash': digest,
                'secret': self.secret.hex(), 'createdAt': self.created_at}
        self._private_write(self.auth_file, json.dumps(data, ensure_ascii=False) + '\n')
        self._private_write(self.code_file, 'Study Atlas 局域网登录码\n' + code + '\n\n只在本机文件中保存，请勿发送到公开群聊或截图。\n')
        return code

    def rotate_secret(self):
        """Invalidate existing sessions while keeping the current login code."""
        try:
            data = json.loads(self.auth_file.read_text())
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        self.secret = secrets.token_bytes(32)
        data['secret'] = self.secret.hex()
        data.setdefault('version', 1)
        data.setdefault('createdAt', self.created_at)
        self._private_write(self.auth_file, json.dumps(data, ensure_ascii=False) + '\n')

    def verify_code(self, code):
        if not isinstance(code, str) or not 4 <= len(code) <= 200:
            return False
        try:
            data = json.loads(self.auth_file.read_text())
            salt = bytes.fromhex(data['salt'])
            expected = str(data['codeHash'])
        except (OSError, ValueError, KeyError):
            return False
        actual = hashlib.sha256(salt + code.encode()).hexdigest()
        return hmac.compare_digest(actual, expected)

    def issue(self):
        expiry = int(time.time()) + self.ttl
        payload = str(expiry)
        signature = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
        return payload + '.' + signature

    def valid_cookie(self, header):
        try:
            cookie = SimpleCookie()
            cookie.load(header or '')
            morsel = cookie.get(COOKIE)
            if not morsel:
                return False
            expiry_text, signature = morsel.value.split('.', 1)
            if int(expiry_text) < int(time.time()):
                return False
            expected = hmac.new(self.secret, expiry_text.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature, expected)
        except (ValueError, TypeError, KeyError):
            return False

    def cookie_header(self, token=None):
        token = token or self.issue()
        return '%s=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=%d' % (COOKIE, token, self.ttl)

    @staticmethod
    def clear_cookie_header():
        return '%s=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT' % COOKIE
