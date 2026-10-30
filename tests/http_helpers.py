"""隔离 HTTP 测试模拟合法页面：先取得本机防伪造令牌。"""
import json
from urllib.parse import urlsplit
from urllib.request import Request as RawRequest, urlopen


def authorized_request(url, data=None, headers=None, method=None, **kwargs):
    headers = dict(headers or {})
    if (method or ('POST' if data is not None else 'GET')).upper() in {'POST','PUT'}:
        parsed = urlsplit(url)
        with urlopen(parsed.scheme + '://' + parsed.netloc + '/api/security') as response:
            token = json.load(response)['token']
        headers.setdefault('X-Study-Atlas-Token', token)
    return RawRequest(url, data=data, headers=headers, method=method, **kwargs)
