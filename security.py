"""本机 Web 边界、请求限流、凭据重定向与受限公开资源读取。"""
import json
import re
import threading
import time
from collections import deque
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

SECURITY_HEADERS = {
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://*.ytimg.com https://*.hdslb.com; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
}


class RateLimiter:
    def __init__(self, clock=time.monotonic):
        self.clock, self.lock, self.events = clock, threading.Lock(), {}

    def allow(self, group, maximum, seconds=60):
        with self.lock:
            now = self.clock(); bucket = self.events.setdefault(group, deque())
            while bucket and bucket[0] <= now - seconds: bucket.popleft()
            if len(bucket) >= maximum: return False
            bucket.append(now); return True


def local_boundary(headers, port, method, path):
    hosts = headers.get_all('Host', [])
    if len(hosts) != 1 or hosts[0] not in {'127.0.0.1:' + str(port), 'localhost:' + str(port)}:
        return False
    origins = headers.get_all('Origin', [])
    if len(origins) > 1 or origins and origins[0] != 'http://' + hosts[0]: return False
    site = headers.get('Sec-Fetch-Site', '')
    callback = path == '/api/youtube/callback' and method == 'GET' and headers.get('Sec-Fetch-Mode') == 'navigate' and headers.get('Sec-Fetch-Dest') == 'document'
    if path.startswith('/api/') and site in {'cross-site', 'same-site'} and not callback: return False
    if method in {'POST', 'PUT'} and site not in {'', 'same-origin'}: return False
    return True


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('JSON 字段重复')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('无效数值')))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ValueError('带凭据的请求不允许重定向，请检查官方服务地址')


def credential_urlopen(request, timeout=30):
    return build_opener(NoRedirect()).open(request, timeout=timeout)


def public_url(url, domains):
    parsed = urlsplit(url)
    if (len(url) > 20000 or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in {None, 443} or any(ord(c) < 33 for c in url)
            or not any(parsed.hostname == d or parsed.hostname.endswith('.' + d) for d in domains)):
        raise ValueError('外部资料地址不在允许的视频平台范围内')
    return url


class PublicRedirects(HTTPRedirectHandler):
    def __init__(self, domains): self.domains = domains
    def redirect_request(self, request, fp, code, message, headers, newurl):
        public_url(newurl, self.domains)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def public_urlopen(request, domains, timeout=30):
    public_url(request.full_url if hasattr(request, 'full_url') else request, domains)
    return build_opener(PublicRedirects(domains)).open(request, timeout=timeout)


def private_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', name):
        raise ValueError('私有配置编号不正确')
    return name
