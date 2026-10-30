"""真实封面与少量视频画面，私有缓存，不调用浏览器或修改播放设置。"""
import hashlib
import bisect
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from integrations import IntegrationError

ASSET = re.compile(r'^[a-f0-9]{64}\.(?:jpg|png|webp)$')


def validate_thumbnail(value):
    if not value: return ''
    if not isinstance(value, str) or len(value) > 3000: raise IntegrationError('封面地址格式不正确')
    p = urlsplit(value)
    if p.scheme != 'https' or p.username or p.password or p.port or not p.hostname or not any(p.hostname == h or p.hostname.endswith('.' + h) for h in ['ytimg.com', 'youtube.com', 'hdslb.com']):
        raise IntegrationError('封面必须来自视频平台的公开图片站点')
    return value


def validate_visuals(value):
    if value is None: return None
    if not isinstance(value, dict) or value.get('status') not in {'ready', 'partial', 'failed'}: raise IntegrationError('图文导学格式不正确')
    cover = value.get('cover', '')
    if cover and (not isinstance(cover, str) or not ASSET.fullmatch(cover)): raise IntegrationError('封面文件编号格式不正确')
    frames = value.get('frames', [])
    if not isinstance(frames, list) or len(frames) > 3: raise IntegrationError('关键画面数量不正确')
    clean = []
    for f in frames:
        if not isinstance(f, dict) or not isinstance(f.get('asset'), str) or not ASSET.fullmatch(f['asset']): raise IntegrationError('画面文件编号格式不正确')
        if type(f.get('timeSec')) is not int or not 0 <= f['timeSec'] <= 3600000: raise IntegrationError('画面时间点格式不正确')
        label, module = f.get('label', '视频画面'), f.get('moduleId', '')
        if not isinstance(label, str) or len(label) > 500 or not isinstance(module, str) or len(module) > 60: raise IntegrationError('画面说明格式不正确')
        clean.append({'asset': f['asset'], 'timeSec': f['timeSec'], 'label': label, 'moduleId': module})
    message = value.get('message', '')
    if not isinstance(message, str) or len(message) > 1000: raise IntegrationError('画面状态说明格式不正确')
    return {'status': value['status'], 'cover': cover, 'frames': clean, 'message': message,
            'createdAt': str(value.get('createdAt', ''))[:50]}


def cache_cover(root, thumbnail):
    thumbnail = validate_thumbnail(thumbnail)
    if not thumbnail: return ''
    folder = Path(root) / '.local/media'; folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = hashlib.sha256(thumbnail.encode()).hexdigest()
    existing = next(iter(folder.glob(key + '.*')), None)
    if existing and ASSET.fullmatch(existing.name): return existing.name
    with urlopen(Request(thumbnail, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com/'}), timeout=20) as response:
        raw = response.read(6 * 1024 * 1024 + 1)
    if len(raw) > 6 * 1024 * 1024: raise IntegrationError('视频封面图片过大')
    ext = 'jpg' if raw.startswith(b'\xff\xd8') else 'png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'webp' if raw.startswith(b'RIFF') and raw[8:12] == b'WEBP' else ''
    if not ext: raise IntegrationError('视频没有返回可用的封面图片')
    asset = key + '.' + ext
    fd = os.open(str(folder / asset), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as f: f.write(raw)
    return asset


def stream_info(url):
    from transcript_sources import ytdlp_command
    try:
        result = subprocess.run(ytdlp_command() + ['--dump-single-json', '--skip-download', '--ignore-no-formats-error', '--', url], capture_output=True, text=True, timeout=100)
        data = json.loads(result.stdout)
    except (ValueError, OSError, subprocess.TimeoutExpired): raise IntegrationError('暂时未取得视频画面，笔记仍可正常阅读')
    formats = [f for f in data.get('formats', []) if f.get('vcodec') not in {None, 'none'} and f.get('ext') == 'mp4' and 0 < (f.get('height') or 0) <= 720 and f.get('protocol') in {'https', 'http'}]
    formats.sort(key=lambda f: (f.get('height', 0), f.get('tbr') or 0), reverse=True)
    for f in formats:
        p = urlsplit(f.get('url', ''))
        if p.scheme == 'https' and not p.username and not p.password and p.hostname and any(p.hostname == d or p.hostname.endswith('.' + d) for d in ['googlevideo.com', 'bilivideo.com', 'bilivideo.cn', 'szbdyd.com']):
            return f['url'], int(data.get('duration') or 0)
    raise IntegrationError('平台当前没有提供适合提取画面的公开视频流，已有笔记保留')


def frame_plan(root, video, duration):
    """依据摘录能匹配到时间时关联模块，否则仅标为视频画面。"""
    p = urlsplit(video['url'])
    key = ('bili-' + p.path.strip('/').split('/')[-1] + '-p' + parse_qs(p.query).get('p', ['1'])[0]) if 'bilibili.com' in (p.hostname or '') else parse_qs(p.query).get('v', [''])[0]
    segments = []
    try: segments = json.loads((Path(root) / '.local/transcripts' / (key + '.json')).read_text()).get('segments', [])
    except (OSError, ValueError): pass
    norm = lambda s: re.sub(r'\s+', '', str(s)).casefold()
    matches, offsets, position = [], [], 0
    for segment in segments:
        offsets.append(position); position += len(norm(segment.get('text', '')))
    transcript = ''.join(norm(x.get('text', '')) for x in segments)
    modules = (video.get('knowledge') or {}).get('modules', [])
    for index, m in enumerate(modules):
        candidates = []
        for quote in m.get('evidence', []):
            quoted = norm(quote)
            found = transcript.find(quoted) if len(quoted) >= 12 else -1
            if found >= 0 and offsets:
                segment = segments[max(0, bisect.bisect_right(offsets, found) - 1)]
                try: time = max(1, min(duration - 1, int(segment['start'])))
                except (ValueError, KeyError, TypeError): continue
                candidates.append({'timeSec': time, 'label': m['title'], 'moduleId': m['id']})
        if candidates:
            # 模块可能引用前置概念；优先选接近该模块课程位置的原文，避免后面模块回跳到开场。
            expected = duration * (index + .5) / len(modules)
            matches.append(min(candidates, key=lambda f: abs(f['timeSec'] - expected)))
    matches.sort(key=lambda f: f['timeSec'])
    matches = list({f['timeSec']: f for f in matches}.values())
    if len(matches) >= 3: return [matches[0], matches[len(matches)//2], matches[-1]]
    return [{'timeSec': max(1, min(duration - 1, int(duration * ratio))), 'label': '视频画面 %d' % i, 'moduleId': ''} for i, ratio in enumerate([.2, .5, .8], 1)]


def build_visuals(store, integrations, vid, progress):
    root = integrations.root; video = next((v for v in store.read()['videos'] if v['id'] == vid), None)
    if not video: raise IntegrationError('视频不存在')
    result = {'status': 'failed', 'cover': '', 'frames': [], 'message': '', 'createdAt': datetime.now(timezone.utc).isoformat()}
    thumbnail = video.get('thumbnail', '')
    if not thumbnail and urlsplit(video['url']).hostname in {'www.youtube.com', 'youtube.com'}:
        yid = parse_qs(urlsplit(video['url']).query).get('v', [''])[0]
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', yid): thumbnail = 'https://i.ytimg.com/vi/' + yid + '/hqdefault.jpg'
    try:
        progress('正在准备视频封面与图文导学')
        result['cover'] = cache_cover(root, thumbnail)
    except Exception: result['message'] = '暂时未取得封面；可稍后补充。'
    try:
        settings = integrations.read('transcription'); runtime = root / settings.get('runtime', '.venv-asr/bin/python')
        if not runtime.is_file(): raise IntegrationError('提取视频画面需要安装本机转录组件')
        stream, duration = stream_info(video['url'])
        if duration < 5: raise IntegrationError('视频太短或时长未识别，暂未生成画面')
        frames = frame_plan(root, video, duration); folder = root / '.local/media'; folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        for f in frames: f['asset'] = hashlib.sha256((video['url'] + ':' + str(f['timeSec'])).encode()).hexdigest() + '.jpg'
        pending = [f for f in frames if not (folder / f['asset']).is_file()]
        if pending:
            progress('正在提取 %d 处真实视频画面，完成后自动加入笔记' % len(pending))
            request = {'url': stream, 'referer': video['url'], 'folder': str(folder), 'frames': pending}
            done = subprocess.run([str(runtime), str(root / 'tools/extract_frames.py')], input=json.dumps(request), text=True, capture_output=True, timeout=180)
            if done.returncode: raise IntegrationError('部分视频画面未能取得，封面与文字笔记保留，可稍后补充')
        result['frames'] = [f for f in frames if (folder / f['asset']).is_file()]
    except IntegrationError as e: result['message'] += str(e)
    except Exception: result['message'] += '画面提取暂未完成，文字笔记正常保留。'
    result['status'] = 'ready' if len(result['frames']) == 3 else 'partial' if result['cover'] or result['frames'] else 'failed'
    if result['status'] == 'ready': result['message'] = '封面与三处原视频画面已保存；画面帮助回顾，笔记依据字幕或转录整理。'
    with store.lock:
        latest = store.read(); target = next((v for v in latest['videos'] if v['id'] == vid), None)
        if not target or target['url'] != video['url']: raise IntegrationError('视频链接已改变，旧画面未覆盖新课程')
        target['visuals'] = validate_visuals(result)
        previous=video.get('automation') or {}
        target['automation'] = previous if previous.get('status') in {'ready','needs_content','failed'} else {'status':'ready' if target.get('summary') else 'needs_content','message':'图文导学已保存' if target.get('summary') else '链接和画面已保存，请补充学习资料继续制作笔记'}
        return store.save(latest)
