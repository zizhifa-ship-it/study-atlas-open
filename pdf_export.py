"""在本机导出带留白的 PDF、无边记逐页图片包和完整视频讲义。"""
import bisect
import io
import json
import os
import re
import subprocess
import sys
import threading
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from integrations import IntegrationError
from note_layout import legacy_cornell
from note_translations import localized_video
from transcript_sources import cached_timing

EXPORT_LOCK = threading.Lock()
EXPORT_KINDS = {"pdf": ("pdf", False), "freeform": ("freeform", False),
                "handout": ("pdf", True), "handout-freeform": ("freeform", True)}


def _time_label(seconds):
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return "%d:%02d:%02d" % (hours, minutes, seconds) if hours else "%d:%02d" % (minutes, seconds)


def _timed_url(url, seconds):
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    host = (parsed.hostname or '').lower()
    if not (host == 'youtu.be' or host.endswith('youtube.com') or host.endswith('bilibili.com')):
        return url
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query['t'] = str(max(0, int(seconds)))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _flat(text):
    return re.sub(r'\s+', '', str(text or '')).casefold()


def _video_chapters(video):
    info = video.get('transcriptInfo') or {}
    explicit = info.get('chapters')
    if isinstance(explicit, list):
        result = [{'start': item['start'], 'title': item['title'], 'summary': ''}
                  for item in explicit if isinstance(item, dict) and type(item.get('start')) is int and isinstance(item.get('title'), str)]
        if result:
            return sorted(result, key=lambda item: item['start'])
    timeline = info.get('timeline')
    lines = [line for line in str(video.get('transcript') or '').splitlines() if line.strip()]
    if not isinstance(timeline, list) or len(timeline) != len(lines):
        return []
    offsets, position, flat_lines = [], 0, []
    for line in lines:
        offsets.append(position)
        flat = _flat(line)
        flat_lines.append(flat)
        position += len(flat)
    transcript = ''.join(flat_lines)
    duration = video.get('durationSec') or (timeline[-1] if timeline else 0)
    modules = (video.get('knowledge') or {}).get('modules', [])
    matches = []
    for index, module in enumerate(modules):
        candidates = []
        for quote in module.get('evidence', []):
            needle = _flat(quote)
            found = transcript.find(needle) if len(needle) >= 12 else -1
            if found >= 0 and offsets:
                line_index = max(0, bisect.bisect_right(offsets, found) - 1)
                if line_index < len(timeline):
                    candidates.append((timeline[line_index], module.get('title', ''), module.get('objective', '')))
        if candidates:
            expected = duration * (index + .5) / max(1, len(modules))
            matches.append(min(candidates, key=lambda item: abs(item[0] - expected)))
    result, seen = [], set()
    for start, title, summary in sorted(matches):
        if start in seen or not title:
            continue
        seen.add(start)
        result.append({'start': start, 'title': title, 'summary': summary})
    return result if len(result) >= 2 else []


def _transcript_blocks(video):
    info = video.get('transcriptInfo') or {}
    lines = [line.strip() for line in str(video.get('transcript') or '').splitlines() if line.strip()]
    timeline = info.get('timeline')
    timed = isinstance(timeline, list) and len(timeline) == len(lines) and bool(lines)
    blocks = []
    if timed:
        return list(zip(timeline, lines))
    current = []
    for line in lines:
        current.append(line)
        if len(' '.join(current)) >= 500:
            blocks.append((None, ' '.join(current)))
            current = []
    if current:
        blocks.append((None, ' '.join(current)))
    return blocks


def _handout_markdown(payload):
    videos = payload.get('videos') or []
    if not videos:
        return ''
    video = videos[0]
    title = video.get('aiTitle') or video.get('title') or '学习视频'
    info = video.get('transcriptInfo') or {}
    lines = ['# ' + title, '', '- 原视频：' + str(video.get('url') or ''),
             '- 作者：' + str(video.get('author') or '未填写')]
    if video.get('durationSec'):
        lines.append('- 时长：' + _time_label(video['durationSec']))
    if info.get('source'):
        lines.append('- 资料来源：' + str(info.get('source')))
    lines += ['', '> 本讲义由本机已保存的字幕与 AI 笔记生成。AI 内容供学习参考，请结合原视频核对。', '']
    if video.get('summary'):
        lines += ['## AI 学习笔记', '', video['summary'], '']
    chapters = _video_chapters(video)
    if chapters:
        lines += ['## 章节目录', '']
        for chapter in chapters:
            link = _timed_url(video.get('url', ''), chapter['start'])
            lines.append('- [%s](%s) · %s' % (_time_label(chapter['start']), link, chapter['title']))
        lines.append('')
    lines += ['## 完整字幕', '']
    for start, text in _transcript_blocks(video):
        if start is None:
            lines.append(text)
        else:
            lines.append('[%s](%s) %s' % (_time_label(start), _timed_url(video.get('url', ''), start), text))
        lines.append('')
    notes = [note for note in video.get('notes', []) if not str(note.get('text', '')).startswith('旧版总结（')]
    if notes:
        lines += ['## 我的补充与批注', '']
        for note in notes:
            prefix = '' if note.get('timeSec') is None else _time_label(note['timeSec']) + ' · '
            lines += ['- ' + prefix + str(note.get('text', '')), '']
    return '\n'.join(lines).rstrip() + '\n'


def select_notes(library, video_id="", language='zh-CN', include_transcript=False):
    videos = [v for v in library["videos"] if not video_id or v["id"] == video_id]
    if video_id and not videos:
        raise IntegrationError("没有找到这个视频")
    selected = [v for v in videos if v.get("summary") or v.get("notes") or v.get("knowledge")
                or (include_transcript and len(str(v.get('transcript') or '').strip()) >= 20)]
    if language != 'zh-CN':
        if not video_id: raise IntegrationError('其他语言笔记请按课程分别导出')
        selected = [localized_video(v, language) for v in selected]
    insights = library.get("insights", []) if not video_id else []
    if not selected and not insights:
        raise IntegrationError("还没有可导出的笔记，请先让 AI 整理视频或获取字幕")
    if len(selected) > 30 or len(insights) > 30:
        raise IntegrationError("一次最多导出 30 条视频和 30 篇归纳，请按课程分别导出")
    fields = ["id", "title", "aiTitle", "author", "url", "categoryId", "durationSec", "summary",
              "notes", "knowledge", "cornell", "transcriptInfo", "visuals"]
    if include_transcript:
        fields.append("transcript")
    return {"videos": [{k: v.get(k, "") for k in fields} for v in selected],
            "categories": library["categories"], "insights": insights,
            "handout": bool(include_transcript),
            "generatedAt": datetime.now(timezone.utc).isoformat()}


def export_notes(library, video_id="", kind="pdf", language='zh-CN'):
    if kind not in EXPORT_KINDS:
        raise IntegrationError("导出格式不支持")
    worker_kind, include_transcript = EXPORT_KINDS[kind]
    if include_transcript and not video_id:
        raise IntegrationError("完整视频讲义请按单门课程导出")
    payload = select_notes(library, video_id, language, include_transcript)
    if not EXPORT_LOCK.acquire(blocking=False):
        raise IntegrationError("正在准备另一份笔记文件，请稍后再试")
    try:
        root = Path(__file__).resolve().parent
        payload["mediaRoot"] = str(root / ".local/media")
        if include_transcript:
            for video in payload["videos"]:
                info = video.get('transcriptInfo') or {}
                if info.get('timeline') and info.get('chapters'):
                    continue
                timeline, chapters = cached_timing(root, video.get('url', ''), video.get('transcript', ''))
                if timeline and not info.get('timeline'):
                    info['timeline'] = timeline
                if chapters and not info.get('chapters'):
                    info['chapters'] = chapters
                video['transcriptInfo'] = info
        candidates = [root / ".venv/Scripts/python.exe", root / ".venv/bin/python", Path(sys.executable),
                      Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"]
        configured = os.environ.get("STUDY_ATLAS_PDF_PYTHON")
        if configured:
            candidates.insert(0, Path(configured))
        for executable in dict.fromkeys(candidates):
            if not executable.is_file():
                continue
            check = subprocess.run([str(executable), "-c", "import reportlab" + (",pypdfium2" if worker_kind == "freeform" else "")], capture_output=True, timeout=15)
            if check.returncode:
                continue
            result = subprocess.run([str(executable), str(root / "pdf_export.py"), "--worker", worker_kind],
                                    input=json.dumps(payload, ensure_ascii=False).encode(), capture_output=True, timeout=150)
            if result.returncode:
                if include_transcript:
                    raise IntegrationError("完整讲义图片生成失败；可先下载讲义 PDF，并检查页数、PDF 依赖与中文字体")
                raise IntegrationError("导出未完成，请检查 PDF 依赖与中文字体，原笔记未受影响")
            if len(result.stdout) > 100 * 1024 * 1024:
                raise IntegrationError("导出文件过大，请按单条视频导出")
            return result.stdout
        raise IntegrationError("首次导出需要安装 PDF 依赖，安装方法见项目的 iPad 与无边记指南")
    except subprocess.TimeoutExpired:
        raise IntegrationError("导出超时，请选择单条视频再试")
    except OSError:
        raise IntegrationError("无法启动本机 PDF 工具，请检查安装")
    finally:
        EXPORT_LOCK.release()


def make_pdf(payload):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, PageBreak, NextPageTemplate, KeepTogether, Flowable, Table, TableStyle, Image

    fonts = [os.environ.get("STUDY_ATLAS_PDF_FONT", ""), str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"), str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/simsun.ttc"), "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
             "/Library/Fonts/Arial Unicode.ttf", "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
             "/usr/share/fonts/truetype/arphic/uming.ttc"]
    font_path = next((p for p in fonts if p and Path(p).is_file()), None)
    if not font_path:
        raise ValueError("A Chinese TTF font is required")
    pdfmetrics.registerFont(TTFont("StudyChinese", font_path))
    pdfmetrics.registerFontFamily("StudyChinese", normal="StudyChinese", bold="StudyChinese", italic="StudyChinese", boldItalic="StudyChinese")
    green, ink, muted = colors.HexColor("#214d3d"), colors.HexColor("#283d34"), colors.HexColor("#728076")
    width, height = A4
    left, bottom, top = 38, 46, height - 62
    body_width = 352
    result = io.BytesIO()
    doc = BaseDocTemplate(result, pagesize=A4, title="学习图谱 · AI 学习笔记", author="学习图谱", leftMargin=left, rightMargin=38, topMargin=62, bottomMargin=46, pageCompression=1)

    def decorate(canvas, document, writing=False, cornell=False):
        canvas.saveState()
        canvas.setFont("StudyChinese", 10)
        canvas.setFillColor(green)
        canvas.drawString(left, height - 32, "学习图谱 / AI 学习笔记")
        canvas.setStrokeColor(colors.HexColor("#dbe4d6"))
        canvas.line(left, height - 42, width - 38, height - 42)
        if not writing and not cornell:
            x, w = left + body_width + 16, width - 38 - (left + body_width + 16)
            canvas.setFillColor(colors.HexColor("#f4f6ee"))
            canvas.roundRect(x, bottom, w, top - bottom, 6, stroke=0, fill=1)
            canvas.setFillColor(muted)
            canvas.setFont("StudyChinese", 9)
            canvas.drawString(x + 10, top - 22, "我的批注")
            canvas.setStrokeColor(colors.HexColor("#dce3d4"))
            y = top - 42
            while y > bottom + 15:
                canvas.line(x + 10, y, x + w - 10, y)
                y -= 21
        elif writing:
            canvas.setStrokeColor(colors.HexColor("#e1e7d9"))
            y = top - 55
            while y > bottom + 16:
                canvas.line(left, y, width - 38, y)
                y -= 24
        canvas.setFont("StudyChinese", 8)
        canvas.setFillColor(muted)
        canvas.drawString(left, 26, "AI 整理供学习参考，请结合原视频核对。")
        canvas.drawRightString(width - 38, 26, "第 %d 页" % document.page)
        canvas.restoreState()

    doc.addPageTemplates([
        PageTemplate(id="cornell", frames=[Frame(left, bottom, width - 76, top - bottom, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=lambda c, d: decorate(c, d, cornell=True)),
        PageTemplate(id="notes", frames=[Frame(left, bottom, body_width, top - bottom, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=decorate),
        PageTemplate(id="writing", frames=[Frame(left, bottom, width - 76, top - bottom, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=lambda c, d: decorate(c, d, True))])
    base = dict(fontName="StudyChinese", textColor=ink, wordWrap="CJK", splitLongWords=True, alignment=TA_LEFT)
    styles = {
        "title": ParagraphStyle("title", fontSize=19, leading=27, spaceAfter=15, **base),
        "h1": ParagraphStyle("h1", fontSize=15, leading=23, spaceBefore=12, spaceAfter=8, keepWithNext=True, **base),
        "h2": ParagraphStyle("h2", fontSize=12, leading=20, spaceBefore=13, spaceAfter=7, keepWithNext=True, **base),
        "text": ParagraphStyle("text", fontSize=10.5, leading=19, spaceAfter=7, **base),
        "transcript": ParagraphStyle("transcript", fontSize=9.2, leading=15, spaceAfter=5, **base),
        "meta": ParagraphStyle("meta", fontSize=8.5, leading=14, spaceAfter=7, fontName="StudyChinese", textColor=muted, wordWrap="CJK", splitLongWords=True)}

    def cornell_table(item, content):
        layout = legacy_cornell(item)
        cue = []
        for i, question in enumerate(layout['cues'], 1):
            cue.extend([Paragraph('%d. %s' % (i, rich(question)), styles['text']), Spacer(1, 15)])
        cue.append(Paragraph('遮住右侧记录，只看提示复述。空白处可写自己的问题。', styles['meta']))
        summary = [Paragraph('归纳小结', styles['h2']), Paragraph(rich(layout['summary']), styles['text'])]
        table = Table([[Paragraph('提示与问题', styles['h2']), Paragraph('课堂记录', styles['h2'])],
                       [cue, content or [Paragraph('资料不足，请补充课程内容。', styles['text'])]], [summary, '']],
                      colWidths=[125, width - 201], repeatRows=1, splitByRow=1, splitInRow=1, hAlign='LEFT',
                      style=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#ecf0df')),
                                        ('BACKGROUND',(0,1),(0,1),colors.HexColor('#f5f7eb')),('BACKGROUND',(1,1),(1,1),colors.HexColor('#fffdf7')),
                                        ('BACKGROUND',(0,2),(-1,2),colors.HexColor('#eef0df')),('SPAN',(0,2),(-1,2)),
                                        ('BOX',(0,0),(-1,-1),0.7,colors.HexColor('#cad5bd')),
                                        ('LINEAFTER',(0,0),(0,1),0.6,colors.HexColor('#cad5bd')),
                                        ('LINEBELOW',(0,0),(-1,0),0.6,colors.HexColor('#cad5bd')),
                                        ('LINEABOVE',(0,2),(-1,2),0.6,colors.HexColor('#cad5bd')),
                                        ('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),
                                        ('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
        return table

    def rich(text):
        text = escape(text, quote=False)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        return text

    def paragraphs(markdown):
        for line in markdown.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("```"):
                continue
            match = re.match(r"^(#{1,6})\s+(.+)", line)
            if match:
                story.append(Paragraph(rich(match.group(2)), styles["h1" if len(match.group(1)) == 1 else "h2"]))
            elif line.startswith("- "):
                story.append(Paragraph("- " + rich(line[2:]), styles["text"]))
            else:
                story.append(Paragraph(rich(line), styles["text"]))

    class BrainDiagram(Flowable):
        def __init__(self, knowledge):
            Flowable.__init__(self)
            self.knowledge = knowledge
            self.width = body_width
            self.height = 105 + ((len(knowledge["modules"]) + 1) // 2) * 150

        def draw(self):
            canvas = self.canv
            def label(text, x, y, width, size=9, count=3):
                lines, current = [], ""
                for ch in text:
                    if pdfmetrics.stringWidth(current + ch, "StudyChinese", size) > width:
                        lines.append(current)
                        current = ""
                    current += ch
                if current:
                    lines.append(current)
                if len(lines) > count:
                    lines = lines[:count]
                    lines[-1] = lines[-1][:-1] + "…"
                canvas.setFont("StudyChinese", size)
                canvas.setFillColor(ink)
                for i, line in enumerate(lines):
                    canvas.drawString(x, y - i * 14, line)
            center = self.width / 2
            root_y = self.height - 48
            canvas.setStrokeColor(colors.HexColor("#adc29b"))
            canvas.setFillColor(colors.HexColor("#e2edca"))
            canvas.roundRect(38, root_y, self.width - 76, 43, 7, stroke=1, fill=1)
            label(self.knowledge["title"], 48, root_y + 27, self.width - 96, 10, 2)
            last_row = (len(self.knowledge["modules"]) - 1) // 2
            canvas.line(center, root_y, center, root_y - 87 - last_row * 150)
            for index, module in enumerate(self.knowledge["modules"]):
                row, col = divmod(index, 2)
                x, y = col * (self.width / 2 + 5), root_y - 45 - row * 150
                card_w = self.width / 2 - 10
                canvas.setStrokeColor(colors.HexColor("#b7cba8"))
                canvas.line(center, y - 42, x + card_w if col == 0 else x, y - 42)
                canvas.setFillColor(colors.HexColor("#f0f5e8"))
                canvas.roundRect(x, y - 105, card_w, 126, 7, stroke=1, fill=1)
                label(module["title"], x + 9, y + 5, card_w - 18, 9, 2)
                for offset, concept in enumerate(module["concepts"][:6]):
                    label(concept["name"], x + 9, y - 31 - offset * 12, card_w - 18, 8, 1)

    def picture(asset, caption):
        from video_media import ASSET
        if not isinstance(asset,str) or not ASSET.fullmatch(asset) or not payload.get('mediaRoot'): return
        path=Path(payload['mediaRoot'])/asset
        if not path.is_file() or path.is_symlink(): return
        try:
            item=Image(str(path));ratio=min((width-76)/item.imageWidth,230/item.imageHeight)
            item.drawWidth=item.imageWidth*ratio;item.drawHeight=item.imageHeight*ratio
            story.append(KeepTogether([item,Spacer(1,7),Paragraph(rich(caption),styles['meta']),Spacer(1,12)]))
        except Exception: pass

    categories = {c["id"]: c for c in payload["categories"]}
    def category_name(cid):
        path, seen = [], set()
        while cid in categories and cid not in seen:
            seen.add(cid)
            c = categories[cid]
            path.insert(0, c["name"])
            cid = c["parentId"]
        return " / ".join(path)

    story = []
    handout = bool(payload.get("handout"))
    for index, video in enumerate(payload["videos"]):
        if story:
            story.append(PageBreak())
        title = video.get("aiTitle") or video["title"]
        info = video.get('transcriptInfo') or {}
        visuals = video.get('visuals') or {}
        chapters = _video_chapters(video) if handout else []
        duration = _time_label(video['durationSec']) if video.get('durationSec') else '时长未标注'
        source_markup = ('资料来源 [S1]：本机导入的课堂文字' if video["url"].startswith("studyatlas://material/")
                         else '视频来源 [S1]：<a href="' + escape(video["url"], quote=True) + '">打开原视频</a>')
        source_detail = ''
        if info:
            source_detail = ('学习资料：' + rich(info.get('source', '')) + ' · ' + rich(info.get('language') or '语言未标注')
                             + ('；语音转录可能包含识别误差' if info.get('kind') == 'asr' else ''))
        if handout:
            story.append(Paragraph('完整视频讲义 / VIDEO STUDY GUIDE', styles['meta']))
            story.append(Spacer(1, 10))
            story.append(Paragraph(rich(title), styles['title']))
            story.append(Paragraph(rich(category_name(video['categoryId'])) + ' · ' + rich(video['author'] or '作者未填写') + ' · ' + duration, styles['meta']))
            story.append(Paragraph(source_markup, styles['meta']))
            if video.get('aiTitle') and video['aiTitle'] != video['title']:
                story.append(Paragraph('原始标题：' + rich(video['title']), styles['meta']))
            if source_detail:
                story.append(Paragraph(source_detail, styles['meta']))
            if visuals.get('cover'):
                picture(visuals.get('cover'), '原视频封面 · [S1]')
            story.append(Paragraph('本讲义包含 AI 学习笔记、章节目录和完整字幕；PDF 可直接插入无边记，素材包中的逐页 PNG 可拖入画布。', styles['meta']))
            if payload.get('generatedAt'):
                story.append(Paragraph('生成日期：' + str(payload['generatedAt'])[:10] + ' · 本机生成，未上传', styles['meta']))
            story.append(PageBreak())
            story.append(Paragraph('AI 学习笔记', styles['h1']))
            story.append(Paragraph(source_markup, styles['meta']))
        else:
            story.append(Paragraph(rich(title), styles["title"]))
            story.append(Paragraph(rich(category_name(video["categoryId"])) + " · " + rich(video["author"] or "作者未填写"), styles["meta"]))
            story.append(Paragraph(source_markup, styles["meta"]))
            if video.get("aiTitle") and video["aiTitle"] != video["title"]:
                story.append(Paragraph("原始标题：" + rich(video["title"]), styles["meta"]))
            if source_detail:
                story.append(Paragraph(source_detail, styles['meta']))
            if visuals.get('cover') or visuals.get('frames'):
                story.append(Paragraph('图文导学', styles['h1']))
                picture(visuals.get('cover'), '原视频封面 · [S1]')
                for frame in visuals.get('frames', []):
                    label = next((m['title'] for m in (video.get('knowledge') or {}).get('modules', []) if m['id'] == frame.get('moduleId')), frame['label'])
                    picture(frame['asset'], '%d:%02d · %s · 原视频画面 [S1]' % (frame['timeSec'] // 60, frame['timeSec'] % 60, label))
        if handout and visuals.get('frames'):
            story.append(Paragraph('原视频画面', styles['h1']))
            for frame in visuals.get('frames', []):
                label = next((m['title'] for m in (video.get('knowledge') or {}).get('modules', []) if m['id'] == frame.get('moduleId')), frame['label'])
                picture(frame['asset'], '%d:%02d · %s · 原视频画面 [S1]' % (frame['timeSec'] // 60, frame['timeSec'] % 60, label))
        if handout:
            story.append(Paragraph('章节目录', styles['h1']))
            if chapters:
                for chapter in chapters:
                    link = _timed_url(video.get('url', ''), chapter['start'])
                    timestamp = '<a href="%s">%s</a>' % (escape(link, quote=True), _time_label(chapter['start']))
                    summary = str(chapter.get('summary') or '')[:200]
                    story.append(Paragraph(timestamp + ' · ' + rich(chapter['title']) + (' · ' + rich(summary) if summary else ''), styles['text']))
                story.append(Paragraph('时间码来自原视频章节或已保存模块的原文依据，点击可回到原视频。', styles['meta']))
            else:
                story.append(Paragraph('原视频没有可读取的章节时间点；完整字幕仍按顺序保留在文末。', styles['meta']))
        if video.get("summary"):
            start = len(story)
            paragraphs(video["summary"])
            content = story[start:]; del story[start:]
            story.append(cornell_table(video, content))
        elif handout:
            story.append(Paragraph('没有 AI 学习笔记；本讲义仍保留章节目录和完整字幕。', styles['text']))
        else:
            start = len(story)
            paragraphs("尚无总结，以下为已保存的补充笔记。")
            content = story[start:]; del story[start:]
            story.append(cornell_table(video, content))
        knowledge = video.get("knowledge")
        if knowledge:
            story.extend([PageBreak(), Paragraph("知识脑图", styles["title"]), Paragraph(rich(knowledge["overview"]), styles["meta"]), BrainDiagram(knowledge), PageBreak(), Paragraph("详尽知识模块", styles["title"])])
            for module in knowledge["modules"]:
                story.append(Paragraph(rich(module["title"]), styles["h1"]))
                story.append(Paragraph("学习目标：" + rich(module["objective"]), styles["meta"]))
                if module["prerequisites"]:
                    story.append(Paragraph("前置知识：" + rich("、".join(module["prerequisites"])), styles["meta"]))
                start = len(story)
                paragraphs(module["notes"])
                if module.get('procedure'):
                    procedure = module['procedure']
                    story.append(Paragraph('实验与操作流程', styles['h2']))
                    paragraphs('目标：' + procedure['goal'])
                    for condition in procedure['requirements']: paragraphs('条件：' + condition)
                    for number, step in enumerate(procedure['steps'], 1):
                        story.append(Paragraph('第 %d 步：%s' % (number, rich(step['action'])), styles['h2']))
                        paragraphs('预期现象：' + step['expected']); paragraphs('验证方法：' + step['verify'])
                    paragraphs('结果与边界：' + procedure['conclusion'])
                for concept in module["concepts"]:
                    story.append(Paragraph("<b>" + rich(concept["name"]) + "：</b>" + rich(concept["explanation"]), styles["text"]))
                if module["examples"]:
                    story.append(Paragraph("课程例子与步骤", styles["h2"]))
                    for text in module["examples"]:
                        paragraphs(text)
                if module["pitfalls"]:
                    story.append(Paragraph("易错点与边界", styles["h2"]))
                    for text in module["pitfalls"]:
                        paragraphs("- " + text)
                if module["questions"]:
                    story.append(Paragraph("复习与参考答案", styles["h2"]))
                    for question in module["questions"]:
                        paragraphs("问题：" + question["question"])
                        paragraphs("参考答案：" + question["answer"])
                if module["evidence"]:
                    story.append(Paragraph("依据摘录 [S1] · " + rich(knowledge["materialKind"]), styles["h2"]))
                    for text in module["evidence"]:
                        story.append(Paragraph(rich(text), styles["meta"]))
                content = story[start:]; del story[start:]
                story.append(cornell_table(module, content))
            story.extend([PageBreak(), Paragraph("AI 自查报告", styles["title"]), Paragraph(rich(knowledge["review"]["summary"]), styles["text"]), Paragraph("AI 自查不保证所有结论正确；摘录匹配只核对文字是否出现，请结合原课检查。", styles["meta"])])
            for issue in knowledge["review"]["issues"]:
                story.append(Paragraph(("已修订" if issue["resolved"] else "待核对") + "：" + rich(issue["problem"]), styles["h2"]))
                paragraphs("核对建议：" + issue["suggestion"])
            if not knowledge["review"]["issues"]:
                paragraphs("本轮没有提出具体问题；关键结论仍需结合原课程核对。")
        for note in video.get("notes", []):
            if note["text"].startswith("旧版总结（"):
                continue  # 旧版本仍留在 JSON，不把历史全文重复印入阅读版。
            story.append(Paragraph("补充笔记" + (" · %d 秒" % note["timeSec"] if note.get("timeSec") is not None else ""), styles["h2"]))
            paragraphs(note["text"])
        if handout:
            story.append(PageBreak())
            story.append(Paragraph('完整字幕', styles['title']))
            transcript_info = info or {}
            transcript_note = ('以下保留全部已保存字幕，未省略后段；时间码可回到原视频。'
                               if transcript_info.get('timeline') else '以下保留全部已保存字幕，未省略后段；这份资料没有逐行时间码。')
            if transcript_info.get('kind') == 'asr':
                transcript_note += ' 本机语音识别可能误听术语、数字与代码，请结合原视频核对。'
            story.append(Paragraph(transcript_note, styles['meta']))
            story.append(Paragraph('资料来源：' + rich(transcript_info.get('source', '未标注')) + ' · ' + rich(transcript_info.get('language') or '语言未标注'), styles['meta']))
            blocks = _transcript_blocks(video)
            for start_seconds, text in blocks:
                if start_seconds is None:
                    story.append(Paragraph(escape(text, quote=False), styles['transcript']))
                else:
                    link = _timed_url(video.get('url', ''), start_seconds)
                    story.append(Paragraph('<a href="%s">%s</a> · %s' % (escape(link, quote=True), _time_label(start_seconds), escape(text, quote=False)), styles['transcript']))
            if not blocks:
                story.append(Paragraph('没有保存可导出的字幕内容。', styles['text']))
            story.append(Paragraph('完整内容到此结束，未省略后段。', styles['meta']))
    for insight in payload["insights"]:
        if story:
            story.append(PageBreak())
        story.append(Paragraph(rich(insight["title"]), styles["title"]))
        paragraphs(insight["content"])
        for source in insight["sources"]:
            label = rich(source["title"]) + "（本地资料）" if source["url"].startswith("studyatlas://material/") else '<a href="' + escape(source["url"], quote=True) + '">' + rich(source["title"]) + '</a>'
            story.append(Paragraph("[" + rich(source["source"]) + "] " + label, styles["meta"]))
    story.extend([NextPageTemplate("writing"), PageBreak(), Paragraph("我的理解与练习", styles["title"]), Paragraph("在无边记里添加手写、箭头和自己的例子；AI 原稿与个人批注分开保留。", styles["meta"])])
    doc.build(story)
    return result.getvalue()


def make_freeform(pdf, payload=None):
    import pypdfium2 as pdfium
    bundle = io.BytesIO()
    document = pdfium.PdfDocument(pdf)
    handout = bool(payload and payload.get('handout'))
    limit = 90 if handout else 60
    try:
        if len(document) > limit:
            if handout:
                raise ValueError("完整讲义页数超过 90 页；PDF 仍可导出，可再按课程分段生成图片")
            raise ValueError("导出页数超过 60 页；请按课程分段生成图片")
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("完整视频讲义.pdf" if handout else "AI学习笔记.pdf", pdf)
            for index in range(len(document)):
                page = document[index]
                bitmap = page.render(scale=2)
                try:
                    image = bitmap.to_pil()
                    content = io.BytesIO()
                    image.save(content, format="PNG")
                    archive.writestr("图片/%03d.png" % (index + 1), content.getvalue())
                finally:
                    bitmap.close()
                    page.close()
            if handout:
                archive.writestr("完整视频讲义.md", _handout_markdown(payload).encode("utf-8"))
            archive.writestr("使用说明.txt", ("学习图谱 · 无边记/笔记软件素材\n\n" + ("这是完整视频讲义，含封面、AI 笔记、章节和完整字幕。\n" if handout else "") + "1. 用 AirDrop 或自行保管的 iCloud 云盘把此文件传到 iPad 或另一台电脑。\n2. 在“文件”中轻点 ZIP 解压，打开“图片”文件夹；每页一张 PNG，按页码排列。\n3. 在无边记新建看板，通过分屏拖入所需 PNG 图片；也可插入 PDF 作为原稿附件。GoodNotes 等支持 PDF/图片的 App 也可导入。\n4. 在画布上添加手写、文本框和连线。PNG 是图片，文字不能直接编辑；PDF 保留可选中的文字。\n5. 看板与批注由无边记管理，不会自动回写学习图谱；如需归档，可从无边记导出带批注的 PDF。\n" + ("6. 如需导入 Obsidian、Notion 等文字笔记软件，可使用“完整视频讲义.md”。\n" if handout else "") + "\nAI 原稿与个人批注请分别保存，不要把个人素材提交到公开 GitHub。\n").encode("utf-8"))
    finally:
        document.close()
    return bundle.getvalue()


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--worker":
    data = json.load(sys.stdin)
    pdf = make_pdf(data)
    sys.stdout.buffer.write(make_freeform(pdf, data) if sys.argv[2] == "freeform" else pdf)
