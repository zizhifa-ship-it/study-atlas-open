"""B 站公开视频：所选分 P 的公开字幕，或可选本机音轨转录。"""
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from integrations import IntegrationError
from functools import partial
from security import public_urlopen

urlopen = partial(public_urlopen, domains=['bilibili.com', 'hdslb.com'])

HOSTS = {'bilibili.com', 'www.bilibili.com', 'm.bilibili.com', 'b23.tv', 'www.b23.tv'}
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com/'}


class ShareRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        u = urlsplit(newurl)
        if u.scheme != 'https' or u.hostname not in HOSTS or u.username or u.password or u.port:
            raise IntegrationError('分享链接跳到了非视频站点，请复制哔哩哔哩视频长链接')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def canonical_bilibili(raw):
    try:
        u = urlsplit(raw)
        if u.scheme not in {'http', 'https'} or u.hostname not in HOSTS or u.username or u.password or u.port: raise ValueError()
        if u.hostname in {'b23.tv', 'www.b23.tv'}:
            if not re.fullmatch(r'/[A-Za-z0-9]{4,32}/?', u.path): raise ValueError()
            try:
                with build_opener(ShareRedirects()).open(Request('https://b23.tv' + u.path, headers=HEADERS), timeout=15) as response:
                    destination = response.geturl()
            except IntegrationError: raise
            except Exception: raise IntegrationError('暂时无法解析 b23.tv 分享链接，请复制视频页面的长链接')
            if urlsplit(destination).hostname in {'b23.tv', 'www.b23.tv'}: raise IntegrationError('分享链接没有返回视频页面，请复制长链接')
            return canonical_bilibili(destination)
        match = re.fullmatch(r'/video/(BV[A-Za-z0-9]{10}|av[0-9]{1,20})/?', u.path)
        if not match: raise ValueError()
        page = parse_qs(u.query).get('p', ['1'])[0]
        if not page.isdigit() or not 1 <= int(page) <= 500: raise ValueError()
        return 'https://www.bilibili.com/video/' + match.group(1) + '/' + ('?p=' + str(int(page)) if int(page) > 1 else '')
    except (ValueError, TypeError, IndexError):
        raise IntegrationError('请填写有效的哔哩哔哩 BV/av 视频链接，分 P 请保留 p 参数')


def get_json(url, limit=4 * 1024 * 1024):
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=25) as response:
            raw = response.read(limit + 1)
        if len(raw) > limit: raise IntegrationError('视频资料过大，请按分 P 或章节处理')
        value = json.loads(raw)
        if not isinstance(value, dict): raise ValueError()
        return value
    except IntegrationError: raise
    except Exception: raise IntegrationError('哔哩哔哩暂时无法提供公开资料，请稍后重试或导入已有转录')


def video_info(url):
    url = canonical_bilibili(url); parsed = urlsplit(url)
    identifier = parsed.path.strip('/').split('/')[-1]
    field, value = ('bvid', identifier) if identifier.startswith('BV') else ('aid', identifier[2:])
    payload = get_json('https://api.bilibili.com/x/web-interface/view?' + urlencode({field: value}))
    data = payload.get('data')
    if payload.get('code') != 0 or not isinstance(data, dict): raise IntegrationError('视频不存在或暂不可公开读取，链接已保留')
    pages = data.get('pages') or []; page = int(parse_qs(parsed.query).get('p', ['1'])[0])
    if not isinstance(pages, list) or not 1 <= page <= len(pages): raise IntegrationError('视频没有这个分 P，请检查链接中的 p 参数')
    part = pages[page - 1]
    if not isinstance(part, dict) or not isinstance(part.get('cid'), int): raise IntegrationError('无法识别该分 P 的视频资料')
    title = str(data.get('title') or '').strip()
    if not title: raise IntegrationError('没有取得视频标题')
    if len(pages) > 1: title += ' · P%d %s' % (page, str(part.get('part') or ''))
    return {'title': title[:500], 'author': str((data.get('owner') or {}).get('name') or '')[:200],
            'durationSec': max(0, int(part.get('duration') or data.get('duration') or 0)), 'thumbnail': str(data.get('pic') or '').replace('http://', 'https://', 1),
            'bvid': str(data.get('bvid') or identifier), 'cid': part['cid'], 'page': page, 'partCount': len(pages), 'url': url}


def subtitle_url(raw):
    if raw.startswith('//'): raw = 'https:' + raw
    u = urlsplit(raw)
    if u.scheme != 'https' or u.username or u.password or u.port or not u.hostname or not any(u.hostname == d or u.hostname.endswith('.' + d) for d in ['hdslb.com', 'bilibili.com']):
        raise IntegrationError('字幕地址不是哔哩哔哩提供的公开字幕地址')
    return raw


def acquire_bilibili(root, url, progress=None, allow_asr=True, force=False):
    from transcript_sources import parse_transcript, run_asr
    progress = progress or (lambda m: None); url = canonical_bilibili(url)
    parsed = urlsplit(url); identity = parsed.path.strip('/').split('/')[-1]; page = int(parse_qs(parsed.query).get('p', ['1'])[0])
    cache = Path(root) / '.local/transcripts'; cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = cache / ('bili-%s-p%d.json' % (identity, page))
    if target.is_file() and not force:
        try:
            data = json.loads(target.read_text()); parse_transcript(data['transcript'])
            return dict(data, cached=True)
        except (ValueError, KeyError, OSError): pass
    progress('正在读取哔哩哔哩所选分 P 的字幕')
    info = video_info(url); data = None
    try:
        payload = get_json('https://api.bilibili.com/x/player/v2?' + urlencode({'bvid': info['bvid'], 'cid': info['cid']}))
        tracks = ((payload.get('data') or {}).get('subtitle') or {}).get('subtitles') or []
        tracks = [t for t in tracks if isinstance(t, dict) and t.get('subtitle_url') and t.get('lan') != 'danmaku']
        tracks.sort(key=lambda t: (0 if t.get('lan') in {'zh', 'zh-CN', 'zh-Hans', 'ai-zh'} else 1, str(t.get('lan', '')).startswith('ai-')))
        for track in tracks[:2]:
            try:
                body = get_json(subtitle_url(track['subtitle_url']))
                transcript = parse_transcript(json.dumps(body, ensure_ascii=False), 'json')
                data = {'transcript': transcript, 'language': str(track.get('lan') or ''), 'source': '哔哩哔哩字幕 · P%d' % page,
                        'kind': 'captions', 'segments': [{'start': x.get('from', 0), 'end': x.get('to', 0), 'text': x.get('content', '')} for x in body.get('body', []) if isinstance(x, dict)]}
                break
            except IntegrationError: continue
    except IntegrationError: pass
    if data is None:
        if not allow_asr: raise IntegrationError('该分 P 没有可公开读取的字幕，可使用本机转录或导入转录文件')
        data = run_asr(root, url, progress)
        data['source'] = '哔哩哔哩视频 · 本机语音转录 · P%d' % page
    data.update(createdAt=datetime.now(timezone.utc).isoformat(), cached=False, partial=False)
    fd, name = tempfile.mkstemp(dir=cache, prefix='.bili-')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as f: json.dump(data, f, ensure_ascii=False)
        os.replace(name, target)
    finally:
        if os.path.exists(name): os.unlink(name)
    return data
