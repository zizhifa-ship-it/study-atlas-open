from security import private_fd_mode
"""原语言字幕优先，缓存优先；可选本机音轨转录，不请求 YouTube 翻译字幕。"""
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from integrations import IntegrationError
from functools import partial
from security import public_urlopen

urlopen = partial(public_urlopen, domains=['youtube.com', 'google.com'])

MAX_TEXT = 200000


def canonical_video(raw):
    try:
        u = urlsplit(raw)
        if u.scheme not in {'http', 'https'} or u.username or u.password or u.port:
            raise ValueError()
        if u.hostname in {'youtu.be', 'www.youtu.be'}:
            vid = u.path.strip('/').split('/')[0]
        elif u.hostname in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
            match = re.fullmatch(r'/(?:shorts|live|embed)/([\w-]{11})/?', u.path)
            vid = match.group(1) if match else parse_qs(u.query).get('v', [''])[0]
        else:
            raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            raise ValueError()
        return vid, 'https://www.youtube.com/watch?v=' + vid
    except (ValueError, IndexError, TypeError):
        raise IntegrationError('自动获取资料目前支持公开 YouTube 视频，其他来源可导入本地转录文件')


captions_time = re.compile(r'(?:(\d{1,3}):)?(\d{1,3}):(\d{2})[.,](\d{1,3})')


def _caption_text(value):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html.unescape(str(value or '')))).strip()


def _caption_seconds(value):
    match = captions_time.search(str(value or ''))
    if not match:
        return None
    hours, minutes, seconds, millis = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis.ljust(3, '0')) / 1000


def _merge_parts(parts):
    merged = []
    for raw in parts:
        text = _caption_text(raw)
        if not text:
            continue
        if merged and text == merged[-1]:
            continue
        if merged and text.startswith(merged[-1] + ' '):
            merged[-1] = text
        else:
            merged.append(text)
    return ' '.join(merged)


def _add_caption(lines, times, text, start=None):
    text = _caption_text(text)
    if not text:
        return
    if lines and text == lines[-1]:
        return
    if lines and text.startswith(lines[-1] + ' '):
        lines[-1] = text
        return
    lines.append(text)
    if start is not None:
        try:
            times.append(max(0, int(round(float(start)))))
        except (TypeError, ValueError):
            pass


def _finish_captions(lines, times):
    text = '\n'.join(lines).strip()
    if not 20 <= len(text) <= MAX_TEXT:
        raise IntegrationError('转录需要 20 至 200000 个字符，请检查内容或按章节导入')
    return text, times if len(times) == len(lines) else []


def parse_timed_transcript(content, extension='txt'):
    """Return transcript lines plus one integer start-second per line when available."""
    if not isinstance(content, str) or len(content) > 4 * 1024 * 1024:
        raise IntegrationError('字幕文件为空或过大，请分章节导入')
    ext = extension.lower().lstrip('.')
    content = content.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    lines, times = [], []
    if ext in {'json3', 'json'}:
        try:
            data = json.loads(content)
        except (ValueError, TypeError):
            raise IntegrationError('字幕 JSON 格式不正确')
        if isinstance(data, dict) and isinstance(data.get('events'), list):
            for event in data['events']:
                if not isinstance(event, dict):
                    continue
                text = ''.join(segment.get('utf8', '') for segment in event.get('segs', []) if isinstance(segment, dict))
                start = event.get('tStartMs')
                _add_caption(lines, times, text, (start / 1000) if isinstance(start, (int, float)) else None)
            return _finish_captions(lines, times)
        if isinstance(data, dict) and isinstance(data.get('body'), list):
            for item in data['body']:
                if isinstance(item, dict):
                    start = item.get('from')
                    _add_caption(lines, times, item.get('content', ''), start)
            return _finish_captions(lines, times)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    start = item.get('start', item.get('from'))
                    _add_caption(lines, times, item.get('text', item.get('content', '')), start)
            return _finish_captions(lines, times)
        raise IntegrationError('字幕 JSON 格式不正确')
    if ext in {'vtt', 'srt'}:
        for block in re.split(r'\n\s*\n', content):
            block_lines = [line for line in block.splitlines() if line.strip()]
            timing = next((i for i, line in enumerate(block_lines) if '-->' in line), None)
            if timing is None:
                continue
            start = _caption_seconds(block_lines[timing].split('-->', 1)[0])
            if start is None:
                continue
            _add_caption(lines, times, _merge_parts(block_lines[timing + 1:]), start)
        if lines:
            return _finish_captions(lines, times)
    for raw in content.splitlines():
        line = _caption_text(raw)
        if not line or '-->' in line or line.isdigit() or line.startswith(('WEBVTT', 'Kind:', 'Language:', 'NOTE', 'STYLE', 'REGION')):
            continue
        if re.match(r'^\d{1,3}:\d{2}(?::\d{2})?[.,]\d{3}', line):
            continue
        _add_caption(lines, times, line)
    return _finish_captions(lines, times)


def parse_transcript(content, extension='txt'):
    return parse_timed_transcript(content, extension)[0]


def normalize_chapters(value, duration=0):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = _caption_text(item.get('title', ''))[:200]
        try:
            start = int(round(float(item.get('start_time', item.get('start', -1)))))
        except (TypeError, ValueError):
            continue
        if not title or start < 0 or (duration and start > float(duration)):
            continue
        result.append({'start': start, 'title': title})
    result.sort(key=lambda item: item['start'])
    unique = {}
    for item in result:
        unique.setdefault(item['start'], item)
    return list(unique.values())[:50]


def timeline_from_segments(data):
    """Old caption caches stored text segments; convert them only when text still matches."""
    segments = data.get('segments') if isinstance(data, dict) else None
    if not isinstance(segments, list):
        return []
    lines, times = [], []
    for segment in segments:
        if isinstance(segment, dict):
            _add_caption(lines, times, segment.get('text', ''), segment.get('start', 0))
    if '\n'.join(lines).strip() != str(data.get('transcript', '')).strip():
        return []
    return times if len(times) == len(lines) else []


def cached_timing(root, url, transcript):
    """Read private local caption timing for export; never fetch or call a model."""
    try:
        vid, _ = canonical_video(url)
    except IntegrationError:
        return [], []
    try:
        data = json.loads((Path(root) / '.local/transcripts' / (vid + '.json')).read_text())
    except (OSError, ValueError):
        return [], []
    if not isinstance(data, dict) or data.get('transcript', '').strip() != str(transcript or '').strip():
        return [], []
    timeline = data.get('timeline') if isinstance(data.get('timeline'), list) else timeline_from_segments(data)
    timeline = [int(value) for value in timeline if isinstance(value, (int, float)) and value >= 0]
    if len(timeline) != len(str(transcript).splitlines()):
        timeline = []
    return timeline, normalize_chapters(data.get('chapters'), data.get('durationSec', 0))


def original_tracks(metadata):
    """tlang 是服务端自动翻译标记，任何语言的翻译轨都排除。"""
    result = []
    primary = str(metadata.get('language') or '').split('-')[0]
    for kind in ['subtitles', 'automatic_captions']:
        for lang, tracks in (metadata.get(kind) or {}).items():
            if lang == 'live_chat' or not isinstance(tracks, list):
                continue
            for track in tracks:
                if not isinstance(track, dict):
                    continue
                url = track.get('url', '')
                parsed = urlsplit(url)
                if parsed.scheme != 'https' or parsed.hostname not in {'www.youtube.com', 'youtube.com', 'video.google.com', 'timedtext.google.com'}:
                    continue
                if 'tlang' in parse_qs(parsed.query) or track.get('is_translated'):
                    continue
                ext = track.get('ext', '')
                if ext not in {'json3', 'vtt', 'srt'}:
                    continue
                rank = (0 if lang.endswith('-orig') else 1 if primary and lang.split('-')[0] == primary else 2,
                        0 if kind == 'subtitles' else 1, {'json3': 0, 'vtt': 1, 'srt': 2}[ext])
                result.append({'language': lang.removesuffix('-orig') if hasattr(lang, 'removesuffix') else lang.replace('-orig', ''),
                               'url': url, 'ext': ext, 'rank': rank})
    return sorted(result, key=lambda t: t['rank'])


def ytdlp_prefix(root=None):
    root = Path(root) if root else Path(__file__).resolve().parent
    name = 'yt-dlp.exe' if os.name == 'nt' else 'yt-dlp'
    folder = 'Scripts' if os.name == 'nt' else 'bin'
    candidates = [shutil.which('yt-dlp'), Path(sys.executable).parent / name,
                  root / '.venv' / folder / name, root / '.venv-asr' / folder / name,
                  Path.home() / '.local/bin/yt-dlp']
    for candidate in candidates:
        if candidate and Path(candidate).is_file(): return [str(candidate)]
    if importlib.util.find_spec('yt_dlp'): return [sys.executable, '-m', 'yt_dlp']
    raise IntegrationError('未安装 yt-dlp，可先导入本地字幕或转录文件')


def ytdlp_command():
    prefix = ytdlp_prefix()
    node = shutil.which('node') or ('/usr/local/bin/node' if Path('/usr/local/bin/node').is_file() else '')
    return prefix + ['--ignore-config', '--no-playlist', '--no-warnings', '--no-progress', '--socket-timeout', '20',
            '--retries', '0', '--extractor-retries', '0', '--extractor-args', 'youtube:skip=translated_subs'] + (['--js-runtimes', 'node:' + node] if node else [])


def asr_status(root):
    root = Path(root)
    path = root / '.local/transcription.json'
    try:
        config = json.loads(path.read_text()) if path.exists() else {}
        runtime = root / config.get('runtime', '.venv-asr/bin/python')
        model_root = root / config.get('downloadRoot', '.local/asr-models')
        ready = bool(config.get('enabled') and runtime.is_file() and any(model_root.rglob('model.bin')))
    except (OSError, ValueError, TypeError):
        ready, config = False, {}
    return {'ready': ready, 'model': config.get('model', 'base'), 'mode': 'local'}


def run_asr(root, url, progress):
    root = Path(root)
    if not asr_status(root)['ready']:
        raise IntegrationError('原语言字幕不可用。本机转录尚未安装，请运行“安装本机转录.command”，或导入 TXT / SRT / VTT 文件继续自动制作笔记')
    config = json.loads((root / '.local/transcription.json').read_text())
    progress('原字幕不可用，正在获取公开音轨供本机语音转录')
    temp_root = root / '.local/transcription-temp'
    temp_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as folder:
        folder = Path(folder)
        try:
            result = subprocess.run(ytdlp_command() + ['--no-write-subs', '--no-write-auto-subs', '-f', 'bestaudio[ext=m4a]/bestaudio',
                                      '--max-filesize', '250M', '--paths', str(folder), '-o', 'source.%(ext)s', '--', url],
                                    capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            raise IntegrationError('音轨获取超时。可导入已有转录文件继续，原有笔记未修改')
        audio = [p for p in folder.glob('source.*') if p.suffix not in {'.part', '.ytdl'}]
        if result.returncode or len(audio) != 1:
            raise IntegrationError('平台暂时无法提供可访问的公开音轨；没有绕过访问限制。可导入已有字幕或转录继续')
        output, status, log = [folder / p for p in ['result.json', 'progress.json', 'worker.log']]
        request = {'audio': str(audio[0]), 'output': str(output), 'progress': str(status), 'model': config.get('model', 'base'),
                   'downloadRoot': str(root / config.get('downloadRoot', '.local/asr-models'))}
        progress('正在本机转录原语言音轨，完成后 AI 会直接整理成中文')
        with log.open('w') as err:
            child = subprocess.Popen([str(root / config.get('runtime', '.venv-asr/bin/python')), str(root / 'tools/transcribe_worker.py')],
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err, text=True)
            try:
                child.stdin.write(json.dumps(request)); child.stdin.close()
                deadline, previous = time.monotonic() + 7200, -1
                while child.poll() is None:
                    if time.monotonic() > deadline:
                        child.terminate(); child.wait(timeout=10)
                        raise IntegrationError('本机转录超过两小时，已停止。请按章节提供音频或转录资料')
                    if status.exists():
                        try:
                            report = json.loads(status.read_text()); minute = int(report.get('seconds', 0) // 60)
                            if minute != previous:
                                progress('本机语音转录：已处理约 %d 分钟音轨，之后自动制作中文笔记' % minute); previous = minute
                        except (OSError, ValueError):
                            pass
                    time.sleep(1)
                if child.returncode or not output.is_file():
                    raise IntegrationError('本机语音转录未完成，请检查转录组件；已保留原有笔记')
                data = json.loads(output.read_text())
            finally:
                if child.poll() is None:
                    child.terminate(); child.wait(timeout=10)
        data['transcript'] = parse_transcript(data.get('transcript', ''))
        segments = data.get('segments')
        if isinstance(segments, list):
            lines, times = [], []
            for segment in segments:
                if isinstance(segment, dict):
                    _add_caption(lines, times, segment.get('text', ''), segment.get('start', 0))
            if lines and len(times) == len(lines):
                data['transcript'] = '\n'.join(lines)
                data['timeline'] = times
            data.pop('segments', None)
        data.update(source='本机语音转录', kind='asr', partial=False, model=config.get('model', 'base'))
        return data


def acquire_transcript(root, url, progress=None, allow_asr=True, force=False):
    progress = progress or (lambda message: None)
    vid, url = canonical_video(url)
    cache = Path(root) / '.local/transcripts'
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = cache / (vid + '.json')
    if target.exists() and not force:
        try:
            saved = json.loads(target.read_text()); parse_transcript(saved['transcript'])
            if not isinstance(saved.get('timeline'), list):
                timeline = timeline_from_segments(saved)
                if timeline:
                    saved['timeline'] = timeline
            return dict(saved, cached=True)
        except (ValueError, KeyError, OSError):
            pass
    progress('正在识别原语言字幕，只请求原字幕轨道，不请求中文自动翻译')
    try:
        result = subprocess.run(ytdlp_command() + ['--dump-single-json', '--skip-download', '--ignore-no-formats-error', '--', url],
                                capture_output=True, text=True, timeout=100)
        metadata = json.loads(result.stdout) if result.stdout.strip() else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        metadata = {}
    chapters = normalize_chapters(metadata.get('chapters'), metadata.get('duration', 0))
    tracks = original_tracks(metadata)
    data = None
    # 每条语言只选一种格式，最多尝试两个原语言轨；429 后停止字幕请求。
    seen = set()
    for track in tracks:
        if track['language'] in seen or len(seen) >= 2:
            continue
        seen.add(track['language'])
        try:
            request = Request(track['url'], headers={'User-Agent': 'Mozilla/5.0', 'Referer': url})
            with urlopen(request, timeout=30) as response:
                raw = response.read(4 * 1024 * 1024 + 1).decode('utf-8-sig')
            transcript, timeline = parse_timed_transcript(raw, track['ext'])
            data = {'transcript': transcript, 'language': track['language'], 'source': 'YouTube 原语言字幕',
                    'kind': 'captions', 'partial': False, 'languageFile': track['language'] + '.' + track['ext'], 'durationSec': metadata.get('duration', 0)}
            if timeline:
                data['timeline'] = timeline
            break
        except HTTPError as exc:
            if exc.code == 429:
                break
        except (URLError, OSError, ValueError):
            continue
    if data is None:
        if not allow_asr:
            raise IntegrationError('没有取得原语言字幕；可启用本机转录或导入已有转录，不需要 YouTube 中文翻译')
        data = run_asr(root, url, progress)
    if chapters and not data.get('chapters'):
        data['chapters'] = chapters
    if not isinstance(data.get('timeline'), list):
        timeline = timeline_from_segments(data)
        if timeline:
            data['timeline'] = timeline
    data.pop('segments', None)
    data.update(createdAt=datetime.now(timezone.utc).isoformat(), cached=False)
    fd, temp = tempfile.mkstemp(dir=cache, prefix='.transcript-')
    try:
        private_fd_mode(fd)
        with os.fdopen(fd, 'w') as out:
            json.dump(data, out, ensure_ascii=False)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return data
