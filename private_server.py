"""Optional single-owner HTTPS deployment entry; local server.py stays unchanged."""
import argparse
import hashlib
import hmac
import json
import os
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from integrations import Integrations, IntegrationError
from lan_auth import LanAuth
from server import ROOT, LibraryStore, make_handler, initialize_local_library


def public_origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in {'', '/'}
            or not re.fullmatch(r'[a-zA-Z0-9.-]+(?::[0-9]{1,5})?', parsed.netloc)):
        raise ValueError('STUDY_ATLAS_PUBLIC_ORIGIN 必须是完整 HTTPS 网站地址，不能含路径、凭据或通配符')
    if parsed.port is not None and not 1 <= parsed.port <= 65535: raise ValueError('网站端口无效')
    return 'https://' + parsed.netloc.lower()


def https_boundary(origin):
    origin = public_origin(origin)
    host = urlsplit(origin).netloc
    def allowed(headers, method, path):
        # The app port must be private. Caddy overwrites forwarded headers at TLS termination.
        if headers.get_all('Host', []) != [host]: return False
        if headers.get_all('X-Forwarded-Proto', []) != ['https']: return False
        origins = headers.get_all('Origin', [])
        if origins and origins != [origin]: return False
        site = headers.get('Sec-Fetch-Site', '')
        if path.startswith('/api/') and site in {'cross-site', 'same-site'}: return False
        if method in {'POST', 'PUT'} and site not in {'', 'same-origin'}: return False
        return True
    return allowed


class PrivateAuth(LanAuth):
    def __init__(self, root, password):
        if (not isinstance(password, str) or not 16 <= len(password) <= 200
                or password.startswith('replace-') or password.isspace()):
            raise ValueError('请设置至少 16 位的独立网站登录口令 STUDY_ATLAS_ACCESS_PASSWORD')
        self.local = Path(root) / '.local'
        if self.local.is_symlink(): raise ValueError('私有目录不能是符号链接')
        self.local.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.local.chmod(0o700)
        self.auth_file = self.local / 'private-auth.json'
        if self.auth_file.is_symlink(): raise ValueError('会话配置不能是符号链接')
        self.ttl = 7 * 24 * 60 * 60
        self._load_or_create_secret()
        try: previous = json.loads(self.auth_file.read_text())
        except (OSError, ValueError): previous = {}
        if not isinstance(previous, dict): previous = {}
        import secrets
        try:
            self.password_salt = bytes.fromhex(previous.get('passwordSalt', ''))
            if len(self.password_salt) != 16: raise ValueError()
        except (TypeError, ValueError): self.password_salt = secrets.token_bytes(16)
        self.password_hash = self._digest(password)
        if previous.get('passwordHash') and previous['passwordHash'] != self.password_hash.hex():
            self.secret = secrets.token_bytes(32)
        self._save()

    def _save(self):
        self._private_write(self.auth_file, json.dumps({'secret': self.secret.hex(),
            'createdAt': self.created_at, 'passwordSalt': self.password_salt.hex(),
            'passwordHash': self.password_hash.hex()}))

    def _digest(self, value):
        return hashlib.pbkdf2_hmac('sha256', value.encode('utf-8'), self.password_salt, 600000)

    def verify_code(self, code):
        return isinstance(code, str) and 16 <= len(code) <= 200 and hmac.compare_digest(self.password_hash, self._digest(code))

    def cookie_header(self, token=None):
        return super().cookie_header(token) + '; Secure'

    @staticmethod
    def clear_cookie_header():
        return LanAuth.clear_cookie_header() + '; Secure'

    def rotate_secret(self):
        import secrets
        self.secret = secrets.token_bytes(32)
        self._save()


class PrivateIntegrations(Integrations):
    def read(self, name):
        value = super().read(name)
        if name == 'ai':
            value.setdefault('mode', 'deepseek')
            value.setdefault('model', 'deepseek-flash')
            if not value.get('apiKey') and os.environ.get('DEEPSEEK_API_KEY'):
                value['apiKey'] = os.environ['DEEPSEEK_API_KEY']
        return value

    def _save_ai(self, data):
        if data.get('mode') == 'harness' or (data.get('mode') == 'compatible' and data.get('compatible', {}).get('provider') in {'ollama', 'lmstudio'}):
            raise IntegrationError('独立服务器模式请使用 DeepSeek 官方 API 或云端兼容接口；本机 Harness 保留在电脑版本使用')
        return super()._save_ai(data)

    def connect_harness(self, url):
        raise IntegrationError('独立服务器模式无需连接本机 Harness，请选择网页 API')

    def check_harness(self):
        raise IntegrationError('独立服务器模式无需 Harness，请使用官方 API 的连接检查')

    def status(self):
        value = super().status()
        if value['ai']['compatible']['provider'] in {'ollama', 'lmstudio'}:
            value['ai']['compatible']['provider'] = 'siliconflow'
        value['deployment'] = {'mode': 'private-server', 'https': True, 'requiresMac': False,
                               'message': '当前是独立服务器，iPad 直接使用网页 API，无需 Mac 或 Harness。'}
        return value


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64
    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(*args, **kwargs)
    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try: super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise
    def process_request_thread(self, request, address):
        try: super().process_request_thread(request, address)
        finally: self.slots.release()


def main():
    parser = argparse.ArgumentParser(description='Private single-owner HTTPS backend; run behind the supplied TLS proxy.')
    parser.add_argument('--bind', default='127.0.0.1', choices=['127.0.0.1', '0.0.0.0'])
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--state', default=os.environ.get('STUDY_ATLAS_STATE_DIR', str(ROOT / 'private-state')))
    args = parser.parse_args()
    try:
        origin = public_origin(os.environ.get('STUDY_ATLAS_PUBLIC_ORIGIN', ''))
        state = Path(args.state)
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        (state / 'data').mkdir(mode=0o700, exist_ok=True)
        template = state / 'data/library.example.json'
        if not template.exists(): template.write_bytes((ROOT / 'data/library.example.json').read_bytes())
        auth = PrivateAuth(state, os.environ.get('STUDY_ATLAS_ACCESS_PASSWORD', ''))
        engine = PrivateIntegrations(state)
        ai = engine.read('ai')
        if ai.get('mode') == 'harness': raise ValueError('独立部署的资料卷不能使用 Harness 模式，请在独立资料卷配置网页 API')
        server = BoundedHTTPServer((args.bind, args.port), make_handler(
            LibraryStore(initialize_local_library(state)), engine, lan=True, auth=auth, access_policy=https_boundary(origin)))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')
    print('Study Atlas private backend ready. Use the configured HTTPS domain and website password.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__': main()
