#!/usr/bin/env python3
"""学习图谱：只依赖 Python 标准库的本地知识库服务。"""

import argparse
import copy
import errno
import json
import os
import re
import secrets
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
from knowledge import validate_knowledge
from practice import validate_learning, practice_overview, grade_answer
from note_layout import clean_cornell
from video_media import validate_thumbnail, validate_visuals, ASSET
from note_translations import validate_translations
from security import SECURITY_HEADERS, RateLimiter, local_boundary, strict_json

ROOT = Path(__file__).resolve().parent
MAX_BODY = 4 * 1024 * 1024
COLORS = {"green", "blue", "purple", "orange"}
STATUSES = {"todo", "learning", "done"}


class ValidationError(ValueError):
    pass


class ConflictError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def string(value, label, limit=500, empty=False):
    require(isinstance(value, str), label + "必须是文字")
    value = value.strip()
    require(empty or bool(value), "请填写" + label)
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
    return {"status": status, "message": string(value.get("message", ""), "整理说明", 1000, True),
            "model": string(value.get("model", ""), "整理模型", 200, True)}


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
            require(parsed.scheme in {"https", "http"} and bool(parsed.hostname)
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
            "transcript": string(video.get("transcript", ""), "字幕或转录", 200000, True),
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
            info = video['transcriptInfo']
            require(isinstance(info, dict) and info.get('kind') in {'captions', 'asr', 'imported'}, '资料来源格式不正确')
            clean_videos[-1]['transcriptInfo'] = {'kind': info['kind'], 'source': string(info.get('source'), '资料来源', 200),
                'language': string(info.get('language', ''), '资料语言', 50, True),
                'createdAt': string(info.get('createdAt', ''), '资料时间', 50, True)}
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
            require(parsed.scheme in {"http", "https"} and bool(parsed.hostname)
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
            # 旧页面或旧备份没有 learning 字段时，不清空新版本的练习记录。
            if isinstance(payload, dict) and "learning" not in payload:
                payload = dict(payload, learning=current["learning"])
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


def make_handler(store, integrations=None):
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

        def respond(self, code, body, content_type="application/json; charset=utf-8", filename=None):
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
            if code == 429: self.send_header('Retry-After', '60')
            self.end_headers()
            self.wfile.write(body)

        def local_request(self):
            try:
                if len(self.path) > 8192: raise ValueError()
                path = urlsplit(self.path).path
            except ValueError:
                self.respond(400, {'error':'请求地址不正确'}); return False
            if not local_boundary(self.headers, self.server.server_port, self.command, path):
                self.respond(403, {"error": "只接受当前本机知识库页面的请求"})
                return False
            if self.command in {'POST','PUT'}:
                values = self.headers.get_all('X-Study-Atlas-Token', [])
                if len(values) != 1 or not re.fullmatch(r'[a-f0-9]{64}', values[0]) or not secrets.compare_digest(values[0], security_token):
                    self.respond(403, {'error':'安全连接已更新，请刷新后重试','code':'security_token'}); return False
                costly = self.command == 'POST' and path not in {'/api/integrations/ai','/api/youtube/client','/api/youtube/disconnect'}
                if not limiter.allow('ai' if costly else 'write', 30 if costly else 180):
                    self.respond(429, {'error':'请求较频繁，请稍后重试'}); return False
            if path == '/api/export' and not limiter.allow('export', 6):
                self.respond(429, {'error':'导出较频繁，请稍后再试'}); return False
            return True

        def read_json_body(self):
            lengths = self.headers.get_all('Content-Length', [])
            require(len(lengths) == 1 and lengths[0].isdigit() and not self.headers.get('Transfer-Encoding'), '请求长度格式不正确')
            length = int(lengths[0]); require(0 < length <= MAX_BODY, '请求内容为空或过大（最多 4 MB）')
            raw = self.rfile.read(length)
            require(len(raw) == length, '请求内容没有完整传输')
            return strict_json(raw)

        def do_GET(self):
            if not self.local_request():
                return
            path = urlsplit(self.path).path
            if path == "/api/health":
                self.respond(200, {"app": "study-atlas", "ok": True})
            elif path == '/api/security':
                self.respond(200, {'token':security_token})
            elif path == "/api/integrations/status":
                self.respond(200, dict(integrations.status(), security={'mode':'local','requestToken':True,'originChecks':True,'contentPolicy':True,'rateLimits':True}))
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
                    self.respond(200, result, "application/zip" if kind == "freeform" else "application/pdf", "无边记学习素材.zip" if kind == "freeform" else "AI学习笔记.pdf")
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
                          "/knowledge.js": ("knowledge.js", "text/javascript; charset=utf-8"),
                          "/practice.js": ("practice.js", "text/javascript; charset=utf-8"),
                          "/exports.js": ("exports.js", "text/javascript; charset=utf-8"),
                          "/cornell.js": ("cornell.js", "text/javascript; charset=utf-8"),
                          "/translations.js": ("translations.js", "text/javascript; charset=utf-8"),
                          "/video-media.js": ("video-media.js", "text/javascript; charset=utf-8"),
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
            try:
                data = self.read_json_body()
                require(isinstance(data, dict), "请求必须是 JSON 对象")
                path = urlsplit(self.path).path
                if path == "/api/import":
                    result = importer.submit(string(data.get("url"), "视频链接", 3000), data.get("retry") is True, data.get("detailed", True) is not False)
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
                    from transcript_sources import parse_transcript
                    vid = string(data.get('videoId'), '视频编号', 100)
                    filename = string(data.get('filename', 'transcript.txt'), '文件名', 200)
                    raw = string(data.get('content'), '字幕或转录', 200000)
                    transcript = parse_transcript(raw, Path(filename).suffix)
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


def main():
    parser = argparse.ArgumentParser(description="学习图谱 · 本地视频知识库")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "library.json")
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = parser.parse_args()
    if args.data == ROOT / "data" / "library.json":
        initialize_local_library(ROOT)
    store = LibraryStore(args.data)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store, Integrations(ROOT)))
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            parser.exit(1, "这个端口已被占用。若知识库已经打开，直接使用原页面；也可添加 --port 8766。\n")
        parser.exit(1, "无法启动本机服务：" + str(exc) + "\n")
    url = "http://127.0.0.1:" + str(server.server_port)
    print("学习图谱已启动：" + url, flush=True)
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
