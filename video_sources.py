"""公开学习视频的链接规范化和资料路由，不读取浏览器登录状态。"""
import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from integrations import IntegrationError
from functools import partial
from security import public_urlopen

urlopen = partial(public_urlopen, domains=['youtube.com'])


def extract_link(raw):
    if not isinstance(raw, str) or len(raw) > 3000: raise IntegrationError('视频链接格式不正确')
    raw = raw.strip()
    links = re.findall(r'https?://[^\s<>，。；）)\]】]+', raw)
    if len(links) > 1: raise IntegrationError('一次请粘贴一条视频链接')
    return links[0] if links else ('https://' + raw if '://' not in raw else raw)


def youtube_url(raw):
    try:
        parsed = urlsplit(extract_link(raw))
        if parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password or parsed.port: raise ValueError()
        if parsed.hostname in {'youtu.be', 'www.youtu.be'}:
            vid = parsed.path.strip('/').split('/')[0]
        elif parsed.hostname in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
            match = re.fullmatch(r'/(shorts|embed|live)/([\w-]{11})/?', parsed.path)
            vid = match.group(2) if match else parse_qs(parsed.query).get('v', [''])[0]
        else: raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid): raise ValueError()
        return 'https://www.youtube.com/watch?v=' + vid
    except (ValueError, IndexError, TypeError):
        raise IntegrationError('请填写公开 YouTube 视频链接')


def canonical_video_url(raw):
    link = extract_link(raw)
    try: host = urlsplit(link).hostname
    except ValueError: raise IntegrationError('视频链接格式不正确')
    if host in {'bilibili.com', 'www.bilibili.com', 'm.bilibili.com', 'b23.tv', 'www.b23.tv'}:
        from bilibili_sources import canonical_bilibili, video_info
        normalized = canonical_bilibili(link)
        if '/video/av' in normalized:
            info = video_info(normalized)
            return 'https://www.bilibili.com/video/' + info['bvid'] + '/' + ('?p=' + str(info['page']) if info['page'] > 1 else '')
        return normalized
    try: return youtube_url(link)
    except IntegrationError: raise IntegrationError('一键整理支持公开 YouTube、哔哩哔哩视频及 b23.tv 分享链接')


def video_metadata(url):
    if urlsplit(url).hostname in {'bilibili.com', 'www.bilibili.com', 'm.bilibili.com'}:
        from bilibili_sources import video_info
        data = video_info(url)
        return {k: data[k] for k in ['title', 'author', 'durationSec', 'thumbnail']}
    endpoint = 'https://www.youtube.com/oembed?' + urlencode({'url': youtube_url(url), 'format': 'json'})
    try:
        with urlopen(Request(endpoint, headers={'User-Agent': 'StudyAtlas/1.0'}), timeout=20) as response:
            result = json.loads(response.read(200000))
        title, author = result.get('title'), result.get('author_name', '')
        if not isinstance(title, str) or not title.strip() or not isinstance(author, str): raise ValueError()
        return {'title': title.strip()[:500], 'author': author.strip()[:200], 'thumbnail': result.get('thumbnail_url', '')}
    except Exception:
        raise IntegrationError('暂时无法识别视频标题，请检查网络或视频是否公开；链接已保存在本机')


def acquire_video_transcript(root, url, progress=None, allow_asr=True, force=False):
    url = canonical_video_url(url)
    if urlsplit(url).hostname == 'www.bilibili.com':
        from bilibili_sources import acquire_bilibili
        return acquire_bilibili(root, url, progress, allow_asr, force)
    from transcript_sources import acquire_transcript
    return acquire_transcript(root, url, progress, allow_asr, force)
