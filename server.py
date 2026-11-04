#!/usr/bin/env python3
"""学习图谱：只依赖 Python 标准库的本地知识库服务。"""

import argparse
import sys
if sys.version_info < (3, 9):
    raise SystemExit('Study Atlas requires Python 3.9 or newer: https://www.python.org/downloads/')
import copy
import errno
import ipaddress
import json
import os
import re
import secrets
import socket
import tempfile
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from integrations import Integrations, IntegrationError
from importer import AutoImporter
from note_results import persist_generation
from pdf_export import export_notes
from papers import lookup_paper
from knowledge import validate_knowledge
from practice import validate_learning, practice_overview, grade_answer
from note_layout import clean_cornell
from video_media import validate_thumbnail, validate_visuals, ASSET
from note_translations import validate_translations, LANGUAGES
from security import SECURITY_HEADERS, RateLimiter, local_boundary, strict_json
from lan_auth import LanAuth
from materials import is_material_url

ROOT = Path(__file__).resolve().parent
MAX_BODY = 4 * 1024 * 1024
COLORS = {"green", "blue", "purple", "orange"}
STATUSES = {"todo", "learning", "done"}
PAPER_STAGES = {"candidate", "screening", "included", "excluded"}
PAPER_READ_STATES = {"unread", "reading", "read"}
RESEARCH_FIELDS = {"question": 5000, "scope": 5000, "searchStrategy": 5000,
                   "inclusion": 5000, "exclusion": 5000, "synthesis": 30000}
PAPER_REVIEW_FIELDS = {"question": 5000, "method": 5000, "data": 5000,
                       "findings": 5000, "limitations": 5000, "relevance": 5000}


class ValidationError(ValueError):
    pass


class ConflictError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def string(value, label, limit=500, empty=False, preserve=False):
    require(isinstance(value, str), label + "必须是文字")
    if not preserve: value = value.strip()
    require(empty or bool(value.strip()), "请填写" + label)
    require(len(value) <= limit, label + "太长了")
    return value


def identifier(value):
    value = string(value, "编号", 100)
    require(bool(re.fullmatch(r"[A-Za-z0-9_-]+", value)), "编号格式不正确")
    return value


def integer(value, label, maximum):
    require(type(value) is int and 0 <= value <= maximum, label + "格式不正确")
    return value


def clean_automation(value):
    require(isinstance(value, dict), "整理进度格式不正确")
    status = value.get("status", "")
    require(status in {"", "queued", "metadata", "transcript", "ai", "ready", "needs_content", "failed"}, "整理状态不正确")
    task = string(value.get('task', ''), '整理任务类型', 50, True)
    from tasks import TASK_NAMES
    require(not task or task in TASK_NAMES or task.startswith('translate:') and task[10:] in LANGUAGES, '整理任务类型不正确')
    return {"status": status, "message": string(value.get("message", ""), "整理说明", 1000, True),
            "model": string(value.get("model", ""), "整理模型", 200, True), **({'task': task} if task else {})}


def clean_transcript_info(value, transcript):
    require(isinstance(value, dict) and value.get('kind') in {'captions', 'asr', 'imported'}, '资料来源格式不正确')
    clean = {'kind': value['kind'], 'source': string(value.get('source'), '资料来源', 200),
             'language': string(value.get('language', ''), '资料语言', 50, True),
             'createdAt': string(value.get('createdAt', ''), '资料时间', 50, True)}
    chapters = value.get('chapters')
    if isinstance(chapters, list):
        result, starts = [], set()
        for item in chapters[:80]:
            if not isinstance(item, dict):
                continue
            title, start = item.get('title'), item.get('start')
            if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
                continue
            if type(start) is not int or not 0 <= start <= 3600000 or start in starts:
                continue
            starts.add(start)
            result.append({'start': start, 'title': title.strip()})
        result.sort(key=lambda item: item['start'])
        if result:
            clean['chapters'] = result[:50]
    timeline = value.get('timeline')
    lines = transcript.splitlines()
    if isinstance(timeline, list) and 0 < len(timeline) <= 5000 and len(timeline) == len(lines):
        if all(type(second) is int and 0 <= second <= 3600000 for second in timeline) and all(first <= second for first, second in zip(timeline, timeline[1:])):
            clean['timeline'] = timeline
    return clean


def clean_web_url(value, label, limit=3000):
    value = string(value, label, limit, True)
    if not value:
        return ''
    parsed = urlsplit(value)
    require(parsed.scheme in {'http', 'https'} and bool(parsed.hostname)
            and not parsed.username and not parsed.password, label + '格式不正确')
    return value


def clean_text_list(value, label, limit, item_limit):
    require(isinstance(value, list) and len(value) <= limit, label + '格式不正确或数量过多')
    result = []
    for item in value:
        text = string(item, label, item_limit).strip()
        if text and text not in result:
            result.append(text)
    return result


def clean_research(value):
    require(isinstance(value, dict), '学术路径格式不正确')
    result = {key: string(value.get(key, ''), key, limit, True, preserve=True) for key, limit in RESEARCH_FIELDS.items()}
    result['updatedAt'] = string(value.get('updatedAt', ''), '学术路径更新时间', 50, True)
    return result


def clean_papers(value, category_ids):
    require(isinstance(value, list) and len(value) <= 10000, '论文格式不正确或数量过多')
    result, ids = [], set()
    for paper in value:
        require(isinstance(paper, dict), '论文格式不正确')
        pid = identifier(paper.get('id'))
        require(pid not in ids, '论文编号重复')
        ids.add(pid)
        authors = clean_text_list(paper.get('authors', []), '作者', 50, 200)
        keywords = clean_text_list(paper.get('keywords', []), '关键词', 30, 60)
        tags = clean_text_list(paper.get('tags', []), '论文标签', 20, 60)
        category_id = paper.get('categoryId') or ''
        if category_id:
            category_id = identifier(category_id)
            require(category_id in category_ids, '论文分类不存在')
        year = paper.get('year')
        if year in (None, ''):
            year = None
        else:
            year = integer(year, '论文年份', 3000)
        doi = string(paper.get('doi', ''), 'DOI', 300, True)
        doi = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', doi, flags=re.I).strip()
        require(not doi or re.fullmatch(r'10\.\d{4,9}/\S+', doi), 'DOI 格式不正确')
        arxiv_id = string(paper.get('arxivId', ''), 'arXiv 编号', 100, True)
        require(not arxiv_id or re.fullmatch(r'[A-Za-z0-9.\-/]+', arxiv_id), 'arXiv 编号格式不正确')
        stage = paper.get('stage', 'candidate')
        require(stage in PAPER_STAGES, '论文阶段不正确')
        read_state = paper.get('readState', 'unread')
        require(read_state in PAPER_READ_STATES, '论文阅读状态不正确')
        review = paper.get('review') or {}
        require(isinstance(review, dict), '论文精读格式不正确')
        clean_review = {key: string(review.get(key, ''), '论文精读', limit, True, preserve=True)
                        for key, limit in PAPER_REVIEW_FIELDS.items()}
        notes = paper.get('notes', [])
        require(isinstance(notes, list) and len(notes) <= 500, '论文笔记格式不正确或数量过多')
        clean_notes, note_ids = [], set()
        for note in notes:
            require(isinstance(note, dict), '论文笔记格式不正确')
            nid = identifier(note.get('id'))
            require(nid not in note_ids, '论文笔记编号重复')
            note_ids.add(nid)
            page = note.get('page')
            if page in (None, ''):
                page = None
            else:
                page = integer(page, '论文页码', 100000)
            quote = string(note.get('quote', ''), '论文摘录', 5000, True, preserve=True)
            text = string(note.get('text', ''), '论文笔记', 30000, True, preserve=True)
            require(quote.strip() or text.strip(), '论文笔记不能为空')
            clean_notes.append({'id': nid, 'page': page, 'quote': quote, 'text': text,
                                'createdAt': string(note.get('createdAt', ''), '论文笔记时间', 50, True)})
        result.append({
            'id': pid, 'title': string(paper.get('title'), '论文标题', 500),
            'authors': authors, 'year': year, 'venue': string(paper.get('venue', ''), '期刊或会议', 300, True),
            'doi': doi, 'arxivId': arxiv_id, 'url': clean_web_url(paper.get('url', ''), '论文链接'),
            'pdfUrl': clean_web_url(paper.get('pdfUrl', ''), '论文 PDF 链接'),
            'abstract': string(paper.get('abstract', ''), '论文摘要', 30000, True, preserve=True),
            'keywords': keywords, 'tags': tags, 'categoryId': category_id,
            'stage': stage, 'readState': read_state,
            'priority': integer(paper.get('priority', 0), '论文优先级', 5),
            'source': string(paper.get('source', ''), '元数据来源', 100, True),
            'review': clean_review, 'notes': clean_notes,
            'createdAt': string(paper.get('createdAt', ''), '论文创建时间', 50, True),
            'updatedAt': string(paper.get('updatedAt', ''), '论文更新时间', 50, True),
        })
    return result


def validate_library(payload):
    """先验证整份数据；任何错误都不能覆盖原文件。"""
    require(isinstance(payload, dict), "数据必须是 JSON 对象")
    require(type(payload.get("schemaVersion")) is int and payload["schemaVersion"] == 1,
            "不支持这个备份版本，请导入学习图谱导出的 JSON 文件")
    revision = integer(payload.get("revision"), "数据版本", 10**12)
    categories, videos = payload.get("categories"), payload.get("videos")
    require(isinstance(categories, list) and len(categories) <= 1000, "分类格式不正确或数量过多")
    require(isinstance(videos, list) and len(videos) <= 10000, "视频格式不正确或数量过多")
    clean_categories, category_ids = [], set()
    for category in categories:
        require(isinstance(category, dict), "分类格式不正确")
        cid = identifier(category.get("id"))
        require(cid not in category_ids, "分类编号重复")
        category_ids.add(cid)
        parent = category.get("parentId")
        if parent is not None:
            parent = identifier(parent)
        color = category.get("color", "green")
        require(color in COLORS, "分类颜色不正确")
        clean_categories.append({
            "id": cid, "name": string(category.get("name"), "分类名称", 60),
            "parentId": parent, "color": color,
            "description": string(category.get("description", ""), "分类说明", 500, True)
        })
    parents = {c["id"]: c["parentId"] for c in clean_categories}
    for category in clean_categories:
        current, seen = category["id"], set()
        while current is not None:
            require(current in parents, "上级分类不存在")
            require(current not in seen, "分类不能互相嵌套成循环")
            seen.add(current)
            current = parents[current]
    clean_videos, video_ids, urls = [], set(), set()
    for video in videos:
        require(isinstance(video, dict), "视频格式不正确")
        vid = identifier(video.get("id"))
        require(vid not in video_ids, "视频编号重复")
        video_ids.add(vid)
        url = string(video.get("url"), "视频链接", 3000)
        try:
            parsed = urlsplit(url)
            require(is_material_url(url) or parsed.scheme in {"https", "http"} and bool(parsed.hostname)
                    and not parsed.username and not parsed.password
                    and not any(ch.isspace() for ch in url), "请填写有效的 http 或 https 视频链接")
        except ValueError:
            raise ValidationError("视频链接格式不正确")
        require(url not in urls, "同一个视频链接已经收藏过了")
        urls.add(url)
        category_id = video.get("categoryId")
        require(category_id in category_ids, "请先创建并选择视频分类")
        status = video.get("status", "todo")
        require(status in STATUSES, "学习状态不正确")
        tags = video.get("tags", [])
        require(isinstance(tags, list) and len(tags) <= 20, "最多添加 20 个标签")
        notes = video.get("notes", [])
        require(isinstance(notes, list) and len(notes) <= 1000, "笔记格式不正确或数量过多")
        clean_notes, note_ids = [], set()
        for note in notes:
            require(isinstance(note, dict), "笔记格式不正确")
            nid = identifier(note.get("id"))
            require(nid not in note_ids, "笔记编号重复")
            note_ids.add(nid)
            time_sec = note.get("timeSec")
            if time_sec is not None:
                time_sec = integer(time_sec, "笔记时间点", 3600000)
            clean_notes.append({
                "id": nid, "timeSec": time_sec,
                "text": string(note.get("text"), "笔记内容", 30000),
                "createdAt": string(note.get("createdAt", ""), "笔记创建时间", 50, True)
            })
        require(type(video.get("favorite", False)) is bool, "收藏状态格式不正确")
        clean_videos.append({
            "id": vid, "title": string(video.get("title"), "视频标题", 500),
            "aiTitle": string(video.get("aiTitle", ""), "中文学习标题", 500, True),
            "url": url, "categoryId": category_id,
            "author": string(video.get("author", ""), "作者", 200, True),
            "durationSec": integer(video.get("durationSec", 0), "视频时长", 3600000),
            "tags": list(dict.fromkeys(string(t, "标签", 60) for t in tags)),
            "status": status, "favorite": video.get("favorite", False),
            "summary": string(video.get("summary", ""), "知识总结", 30000, True),
            "transcript": string(video.get("transcript", ""), "字幕或转录", 800000, True, preserve=True),
            "automation": clean_automation(video.get("automation", {})),
            "knowledge": validate_knowledge(video.get("knowledge")),
            "notes": clean_notes,
            "createdAt": string(video.get("createdAt", ""), "创建时间", 50, True),
            "updatedAt": string(video.get("updatedAt", ""), "更新时间", 50, True)
        })
        if video.get('thumbnail'):
            clean_videos[-1]['thumbnail']=validate_thumbnail(video['thumbnail'])
        if video.get('visuals') is not None:
            clean_videos[-1]['visuals']=validate_visuals(video['visuals'])
        if video.get('cornell') is not None:
            clean_videos[-1]['cornell'] = clean_cornell(video['cornell'])
        if video.get('transcriptInfo') is not None:
            clean_videos[-1]['transcriptInfo'] = clean_transcript_info(video['transcriptInfo'], clean_videos[-1]['transcript'])
        if video.get('translations') is not None:
            clean_videos[-1]['translations'] = validate_translations(video['translations'], clean_videos[-1])
    insights = payload.get("insights", [])
    require(isinstance(insights, list) and len(insights) <= 3000, "经验归纳格式不正确或数量过多")
    clean_insights, insight_ids = [], set()
    for item in insights:
        require(isinstance(item, dict), "经验归纳格式不正确")
        iid = identifier(item.get("id"))
        require(iid not in insight_ids, "经验归纳编号重复")
        insight_ids.add(iid)
        sources = item.get("sources", [])
        require(isinstance(sources, list) and len(sources) <= 12, "归纳来源格式不正确")
        clean_sources = []
        for source in sources:
            require(isinstance(source, dict), "来源格式不正确")
            url = string(source.get("url"), "来源链接", 3000)
            parsed = urlsplit(url)
            require(is_material_url(url) or parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                    and not parsed.username and not parsed.password, "来源链接不正确")
            clean_sources.append({"source": string(source.get("source"), "来源编号", 20),
                                  "videoId": identifier(source.get("videoId")),
                                  "title": string(source.get("title"), "来源标题", 500), "url": url})
        clean_insights.append({"id": iid, "title": string(item.get("title"), "经验标题", 300),
                               "content": string(item.get("content"), "经验内容", 30000),
                               "sources": clean_sources,
                               "model": string(item.get("model", ""), "模型", 200, True),
                               "createdAt": string(item.get("createdAt", ""), "生成时间", 50, True)})
    return {"schemaVersion": 1, "revision": revision,
            "categories": clean_categories, "videos": clean_videos, "insights": clean_insights,
            "papers": clean_papers(payload.get("papers", []), category_ids),
            "research": clean_research(payload.get("research") or {}),
            "learning": validate_learning(payload.get("learning"))}


class LibraryStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        if not self.path.exists():
            raise FileNotFoundError("找不到数据文件：" + str(self.path))
        self.read()

    def read(self):
        with self.lock:
            return validate_library(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, payload):
        with self.lock:
            current = self.read()
            # 旧页面或旧备份缺少这些扩展字段时，不清空已有记录。
            if isinstance(payload, dict):
                preserved = {key: current[key] for key in ('learning', 'papers', 'research') if key not in payload}
                if preserved:
                    payload = dict(payload, **preserved)
            clean = validate_library(payload)
            if clean["revision"] != current["revision"]:
                raise ConflictError("数据已在另一个页面更新。请刷新后再修改；当前填写内容还在窗口中。")
            clean["revision"] += 1
            backups = self.path.parent / ".backups"
            backups.mkdir(mode=0o700, exist_ok=True)
            require(not backups.is_symlink(), '备份目录不能使用符号链接')
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            backup_fd = os.open(str(backups / (stamp + ".json")), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(backup_fd, "w", encoding="utf-8") as backup:
                json.dump(current, backup, ensure_ascii=False, indent=2)
                backup.write("\n")
            tmp_name = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent,
                                                 prefix=".library-", suffix=".tmp", delete=False) as tmp:
                    tmp_name = tmp.name
                    json.dump(clean, tmp, ensure_ascii=False, indent=2)
                    tmp.write("\n")
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(tmp_name, self.path)
            finally:
                if tmp_name and os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            for old in sorted(backups.glob("*.json"))[:-30]:
                old.unlink()
            return copy.deepcopy(clean)


def make_handler(store, integrations=None, lan=False, auth=None):
    integrations = integrations or Integrations(store.path.parent / "test-integrations")
    importer = AutoImporter(store, integrations)
    security_token, limiter = secrets.token_hex(32), RateLimiter()
    class Handler(BaseHTTPRequestHandler):
        server_version = "StudyAtlas/1.0"
        sys_version = ''

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, message, *args):
            # OAuth 回调参数不进入终端日志。
            safe = tuple(re.sub(r'[\x00-\x1f\x7f-\x9f]', '?', re.sub(r'\?\S+', '?[hidden]', str(a)))[:1000] for a in args)
            super().log_message(message, *safe)

        def respond(self, code, body, content_type="application/json; charset=utf-8", filename=None, extra_headers=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if filename:
                from urllib.parse import quote
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8" + chr(39) * 2 + quote(filename))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            for name, value in SECURITY_HEADERS.items(): self.send_header(name, value)
            for name, value in (extra_headers or {}).items(): self.send_header(name, value)
            if code == 429: self.send_header('Retry-After', '60')
            self.end_headers()
            self.wfile.write(body)

        def authenticated(self):
            return not lan or bool(auth and auth.valid_cookie(self.headers.get('Cookie', '')))

        def local_request(self):
            try:
                if len(self.path) > 8192: raise ValueError()
                path = urlsplit(self.path).path
            except ValueError:
                self.respond(400, {'error':'请求地址不正确'}); return False
            if not local_boundary(self.headers, self.server.server_port, self.command, path, lan=lan):
                self.respond(403, {"error": "只接受本机或已授权的局域网页面请求"})
                return False
            if self.command in {'POST','PUT'}:
                session_path = lan and path in {'/api/session', '/api/session/logout'}
                if not session_path:
                    values = self.headers.get_all('X-Study-Atlas-Token', [])
                    if len(values) != 1 or not re.fullmatch(r'[a-f0-9]{64}', values[0]) or not secrets.compare_digest(values[0], security_token):
                        self.respond(403, {'error':'安全连接已更新，请刷新后重试','code':'security_token'}); return False
                costly = self.command == 'POST' and path not in {'/api/integrations/ai','/api/youtube/client','/api/youtube/disconnect'}
                if not limiter.allow('ai' if costly else 'write', 30 if costly else 180):
                    self.respond(429, {'error':'请求较频繁，请稍后重试'}); return False
            if path == '/api/export' and not limiter.allow('export', 6):
                self.respond(429, {'error':'导出较频繁，请稍后再试'}); return False
            return True

        def login_page(self):
            return self.respond(200, (ROOT / 'login.html').read_bytes(), 'text/html; charset=utf-8')

        def read_json_body(self):
            lengths = self.headers.get_all('Content-Length', [])
            require(len(lengths) == 1 and lengths[0].isdigit() and not self.headers.get('Transfer-Encoding'), '请求长度格式不正确')
            limit = 12 * 1024 * 1024 if urlsplit(self.path).path == '/api/material/pdf' else MAX_BODY
            length = int(lengths[0]); require(0 < length <= limit, '请求内容为空或过大')
            raw = self.rfile.read(length)
            require(len(raw) == length, '请求内容没有完整传输')
            return strict_json(raw)

        def do_GET(self):
            if not self.local_request():
                return
            path = urlsplit(self.path).path
            if lan and not self.authenticated():
                if path == '/api/session':
                    self.respond(200, {'authenticated': False, 'lan': True})
                elif path in {'/login', '/login.html'}:
                    self.login_page()
                elif path == '/login.js':
                    self.respond(200, (ROOT / 'login.js').read_bytes(), 'text/javascript; charset=utf-8')
                elif path == '/':
                    self.login_page()
                elif path == '/favicon.svg':
                    self.respond(200, (ROOT / 'favicon.svg').read_bytes(), 'image/svg+xml')
                else:
                    self.respond(401, {'error': '请先在局域网登录页输入登录码'})
                return
            if lan and path in {'/login', '/login.html'}:
                self.respond(302, b'', extra_headers={'Location': '/'})
                return
            if path == '/api/session':
                self.respond(200, {'authenticated': True, 'lan': lan})
            elif path == "/api/health":
                self.respond(200, {"app": "study-atlas", "ok": True})
            elif path == '/api/security':
                self.respond(200, {'token':security_token})
            elif path == "/api/integrations/status":
                self.respond(200, dict(integrations.status(), security={'mode':'lan' if lan else 'local','login':lan,'requestToken':True,'originChecks':True,'contentPolicy':True,'rateLimits':True}))
            elif path == '/api/tasks':
                from tasks import task_snapshot
                self.respond(200, task_snapshot(importer))
            elif path == '/api/setup/status':
                from diagnostics import readiness
                self.respond(200, readiness(getattr(integrations, 'root', ROOT), integrations))
            elif path == "/api/youtube/callback":
                try:
                    integrations.youtube_callback(parse_qs(urlsplit(self.path).query))
                    self.respond(200, "<meta charset='utf-8'><title>YouTube 已连接</title><h1>YouTube 已连接</h1><p>已获得只读权限。可以关闭此页，回到学习图谱读取播放列表。</p>", "text/html; charset=utf-8")
                except IntegrationError as exc:
                    import html
                    self.respond(400, "<meta charset='utf-8'><title>授权未完成</title><h1>授权未完成</h1><p>" + html.escape(str(exc)) + "</p>", "text/html; charset=utf-8")
            elif path.startswith("/api/youtube/"):
                query = parse_qs(urlsplit(self.path).query)
                try:
                    if path == "/api/youtube/account":
                        result = integrations.youtube_account()
                    elif path == "/api/youtube/playlists":
                        result = integrations.youtube_playlists(query.get("pageToken", [""])[0])
                    elif path == "/api/youtube/playlist-items":
                        result = integrations.youtube_playlist_items(query.get("id", [""])[0], query.get("pageToken", [""])[0])
                    else:
                        self.respond(404, {"error": "接口不存在"})
                        return
                    self.respond(200, result)
                except IntegrationError as exc:
                    self.respond(400, {"error": str(exc)})
            elif path == "/api/export":
                query = parse_qs(urlsplit(self.path).query)
                try:
                    kind = query.get("format", ["pdf"])[0]
                    result = export_notes(store.read(), query.get("videoId", [""])[0], kind, query.get('language', ['zh-CN'])[0])
                    if kind in {'freeform', 'handout-freeform'}:
                        filename = '完整视频讲义_无边记素材.zip' if kind == 'handout-freeform' else '无边记学习素材.zip'
                        self.respond(200, result, "application/zip", filename)
                    elif kind in {'pdf', 'handout'}:
                        filename = '完整视频讲义.pdf' if kind == 'handout' else 'AI学习笔记.pdf'
                        self.respond(200, result, "application/pdf", filename)
                    else:
                        raise IntegrationError('导出格式不支持')
                except IntegrationError as exc:
                    self.respond(400, {"error": str(exc)})
            elif path.startswith('/api/media/'):
                if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                    self.respond(403, {'error':'只允许从本机知识库读取画面'})
                    return
                name=path.removeprefix('/api/media/')
                target=integrations.root/'.local/media'/name if ASSET.fullmatch(name) else None
                if not target or not target.is_file() or target.is_symlink():
                    self.respond(404,{'error':'画面尚未保存，可重新生成图文导学'})
                else:
                    self.respond(200,target.read_bytes(),{'jpg':'image/jpeg','png':'image/png','webp':'image/webp'}[target.suffix[1:]])
            elif path == "/api/library":
                try:
                    self.respond(200, store.read())
                except (OSError, ValueError, IntegrationError):
                    self.respond(500, {"error": "无法读取资料，请检查数据文件或恢复备份"})
            elif path == "/api/learning":
                try:
                    self.respond(200, practice_overview(store.read()))
                except (OSError, ValueError, IntegrationError):
                    self.respond(500, {"error": "无法读取复习记录，请检查数据或恢复备份"})
            else:
                assets = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/index.html": ("index.html", "text/html; charset=utf-8"),
                          "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/harness-models.js": ("harness-models.js", "text/javascript; charset=utf-8"),
                          "/api-client.js": ("api-client.js", "text/javascript; charset=utf-8"),
                          "/file-import.js": ("file-import.js", "text/javascript; charset=utf-8"),
                          "/knowledge.js": ("knowledge.js", "text/javascript; charset=utf-8"),
                          "/practice.js": ("practice.js", "text/javascript; charset=utf-8"),
                          "/exports.js": ("exports.js", "text/javascript; charset=utf-8"),
                          "/cornell.js": ("cornell.js", "text/javascript; charset=utf-8"),
                          "/translations.js": ("translations.js", "text/javascript; charset=utf-8"),
                          "/video-media.js": ("video-media.js", "text/javascript; charset=utf-8"),
                          "/login.js": ("login.js", "text/javascript; charset=utf-8"),
                          "/favicon.svg": ("favicon.svg", "image/svg+xml")}
                if path not in assets:
                    self.respond(404, {"error": "页面不存在"})
                    return
                name, mime = assets[path]
                self.respond(200, (ROOT / name).read_bytes(), mime)

        def do_POST(self):
            if not self.local_request():
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self.respond(415, {"error": "只接受 JSON 数据"})
                return
            path = urlsplit(self.path).path
            if lan and not self.authenticated() and path not in {'/api/session', '/api/session/logout'}:
                self.respond(401, {'error': '登录已过期，请回到局域网登录页重新登录'})
                return
            try:
                data = self.read_json_body()
                require(isinstance(data, dict), "请求必须是 JSON 对象")
                if path == '/api/session':
                    if not lan:
                        self.respond(404, {'error': '当前是本机模式，不需要登录'})
                    elif not limiter.allow('login', 6):
                        self.respond(429, {'error': '登录尝试过多，请稍后再试'})
                    elif not auth.verify_code(data.get('code')):
                        self.respond(401, {'error': '登录码不正确'})
                    else:
                        self.respond(200, {'authenticated': True}, extra_headers={'Set-Cookie': auth.cookie_header()})
                    return
                elif path == '/api/session/logout':
                    if lan and auth:
                        auth.rotate_secret()
                    self.respond(200, {'authenticated': False}, extra_headers={'Set-Cookie': LanAuth.clear_cookie_header()})
                    return
                elif path == "/api/import":
                    result = importer.submit(string(data.get("url"), "视频链接", 3000), data.get("retry") is True, data.get("detailed", True) is not False)
                elif path == '/api/tasks/resume':
                    result = importer.resume(string(data.get('videoId'), '视频编号', 100))
                elif path == '/api/material/pdf':
                    from pdf_import import read_pdf_upload
                    result = read_pdf_upload(data)
                elif path == '/api/material/course':
                    result = importer.submit_material(data)
                elif path == '/api/papers/lookup':
                    result = lookup_paper(string(data.get('query'), 'DOI 或 arXiv 编号', 3000))
                elif path == '/api/integrations/compatible/models':
                    result = integrations.compatible_models(data.get('compatible'))
                elif path == "/api/knowledge/build":
                    result = importer.submit_knowledge(string(data.get("videoId"), "视频编号", 100), data.get("reviewOnly") is True)
                elif path == '/api/knowledge/format':
                    result = importer.submit_format(string(data.get('videoId'), '视频编号', 100))
                elif path == '/api/media/build':
                    result = importer.submit_visuals(string(data.get('videoId'), '视频编号', 100))
                elif path == '/api/notes/translate':
                    result = importer.submit_translation(string(data.get('videoId'), '视频编号', 100), string(data.get('language'), '目标语言', 20))
                elif path == "/api/learning/grade":
                    result = grade_answer(store, integrations, data)
                elif path in {"/api/integrations/harness/connect", "/api/integrations/harness/check", "/api/integrations/ai"}:
                    # 覆盖一键导入中各模型阶段之间的间隙，以及等待中的任务。
                    with importer.lock:
                        if importer.queue.unfinished_tasks:
                            raise IntegrationError('整理队列正在运行，请全部完成后修改 AI 设置或刷新模型列表')
                        if path.endswith('/connect'):
                            result = integrations.connect_harness(string(data.get("url"), "Harness 启动链接", 4000))
                        elif path.endswith('/check'):
                            result = integrations.check_harness()
                        else:
                            result = integrations.save_ai(data)
                elif path == "/api/ai/generate":
                    original = store.read()
                    result = integrations.generate(data, original)
                    if data.get("save", True) is not False:
                        result = persist_generation(store, data, result, original)
                elif path == "/api/ai/transcript":
                    target = next((v for v in store.read()["videos"] if v["id"] == data.get("videoId")), None)
                    require(target is not None, "视频不存在")
                    result = integrations.transcript(target["url"])
                elif path == '/api/material/import':
                    from materials import parse_material
                    vid = string(data.get('videoId'), '视频编号', 100)
                    filename = string(data.get('filename', 'transcript.txt'), '文件名', 200)
                    raw = string(data.get('content'), '字幕或转录', 800000, preserve=True)
                    _, _, transcript = parse_material({'title':'补充学习资料','filename':filename,'content':raw})
                    with store.lock:
                        latest = store.read(); target = next((v for v in latest['videos'] if v['id'] == vid), None)
                        require(target is not None, '视频不存在')
                        target['transcript'] = transcript
                        target['transcriptInfo'] = {'kind': 'imported', 'source': '导入的字幕或转录文件', 'language': '', 'createdAt': datetime.now(timezone.utc).isoformat()}
                        saved = store.save(latest)
                    if data.get('generate', True) is not False:
                        try:
                            from video_sources import canonical_video_url
                            canonical_video_url(target['url'])
                        except IntegrationError:
                            result = importer.submit_knowledge(vid)
                        else:
                            result = importer.submit(target['url'], True, True)
                    else:
                        result = {'library': saved, 'videoId': vid}
                elif path == "/api/youtube/client":
                    result = integrations.save_youtube_client(data)
                elif path == "/api/youtube/auth-url":
                    result = integrations.youtube_auth_url(self.server.server_port)
                elif path == "/api/youtube/disconnect":
                    token = integrations.local / "youtube-token.json"
                    if token.exists():
                        token.unlink()
                    result = integrations.status()
                else:
                    self.respond(404, {"error": "接口不存在"})
                    return
                self.respond(200, result)
            except (ValidationError, IntegrationError) as exc:
                self.respond(400, {"error": str(exc)})
            except (ValueError, TypeError, UnicodeError, KeyError, RecursionError):
                self.respond(400, {"error": "请求或服务响应格式不正确"})
            except Exception:
                self.respond(500, {"error": "连接服务时发生错误，请检查本机服务与设置后重试"})

        def do_PUT(self):
            if not self.local_request():
                return
            if lan and not self.authenticated():
                self.respond(401, {'error': '登录已过期，请回到局域网登录页重新登录'})
                return
            if urlsplit(self.path).path != "/api/library":
                self.respond(404, {"error": "接口不存在"})
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self.respond(415, {"error": "只接受 JSON 数据"})
                return
            try:
                payload = self.read_json_body()
                self.respond(200, store.save(payload))
            except ConflictError as exc:
                self.respond(409, {"error": str(exc)})
            except (ValueError, TypeError, UnicodeError, IntegrationError, RecursionError) as exc:
                self.respond(400, {"error": str(exc) if isinstance(exc, (ValidationError, IntegrationError)) else "JSON 数据格式不正确"})
            except OSError:
                self.respond(500, {"error": "保存失败，请检查文件权限或磁盘空间"})

    return Handler


def initialize_local_library(root):
    """公开仓库只带空白模板，首次运行创建私有副本；绝不覆盖已有资料。"""
    path = Path(root) / "data" / "library.json"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    initial = (path.parent / "library.example.json").read_text(encoding="utf-8")
    validate_library(json.loads(initial))
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(initial)
    return path


def lan_ipv4_addresses():
    candidates = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.add(info[4][0])
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(('192.168.1.1', 80))
            candidates.add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    result = []
    private_networks = [ipaddress.ip_network(net) for net in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10')]
    for value in candidates:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if isinstance(address, ipaddress.IPv4Address) and any(address in network for network in private_networks):
            result.append(value)
    return sorted(set(result))


def main():
    parser = argparse.ArgumentParser(description="学习图谱 · 本地视频知识库")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "library.json")
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    parser.add_argument("--lan", action="store_true", help="允许同一局域网设备通过登录码访问；绑定 0.0.0.0")
    args = parser.parse_args()
    if args.data == ROOT / "data" / "library.json":
        initialize_local_library(ROOT)
    store = LibraryStore(args.data)
    auth = LanAuth(ROOT) if args.lan else None
    host = '0.0.0.0' if args.lan else '127.0.0.1'
    try:
        server = ThreadingHTTPServer((host, args.port), make_handler(store, Integrations(ROOT), lan=args.lan, auth=auth))
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            parser.exit(1, "这个端口已被占用。若知识库已经打开，直接使用原页面；也可添加 --port 8766。\n")
        parser.exit(1, "无法启动本机服务：" + str(exc) + "\n")
    url = "http://127.0.0.1:" + str(server.server_port)
    print("学习图谱已启动：" + url, flush=True)
    if args.lan:
        print("局域网模式：仅接受私网 / .local 主机，必须先输入登录码。", flush=True)
        print("登录码文件：" + str(auth.code_file), flush=True)
        for address in lan_ipv4_addresses():
            print("iPad / 其他设备（IP）：" + "http://" + address + ":" + str(server.server_port) + "/", flush=True)
        bonjour = socket.gethostname().rstrip('.').lower()
        if bonjour.endswith('.local'):
            print("iPad / 其他设备（Bonjour，推荐）：http://" + bonjour + ":" + str(server.server_port) + "/", flush=True)
        print("如果 macOS 防火墙询问，请只在信任的专用网络允许；不要做公网端口转发。", flush=True)
    print("资料保存在：" + str(store.path), flush=True)
    print("保持此窗口运行；按 Control+C 停止。", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止，学习资料已保留。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
