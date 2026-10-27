"""在本机导出带留白的 PDF 和适合无边记的逐页图片包。"""
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import threading
import zipfile
from html import escape
from pathlib import Path
from integrations import IntegrationError

EXPORT_LOCK = threading.Lock()


def select_notes(library, video_id=""):
    videos = [v for v in library["videos"] if not video_id or v["id"] == video_id]
    if video_id and not videos:
        raise IntegrationError("没有找到这个视频")
    selected = [v for v in videos if v.get("summary") or v.get("notes") or v.get("knowledge")]
    insights = library.get("insights", []) if not video_id else []
    if not selected and not insights:
        raise IntegrationError("还没有可导出的笔记，请先让 AI 整理视频")
    if len(selected) > 30 or len(insights) > 30:
        raise IntegrationError("一次最多导出 30 条视频和 30 篇归纳，请按课程分别导出")
    return {"videos": [{k: v.get(k, "") for k in ["id", "title", "aiTitle", "author", "url", "categoryId", "summary", "notes", "knowledge"]} for v in selected],
            "categories": library["categories"], "insights": insights}


def export_notes(library, video_id="", kind="pdf"):
    if kind not in {"pdf", "freeform"}:
        raise IntegrationError("导出格式不支持")
    payload = select_notes(library, video_id)
    if not EXPORT_LOCK.acquire(blocking=False):
        raise IntegrationError("正在准备另一份笔记文件，请稍后再试")
    try:
        root = Path(__file__).resolve().parent
        candidates = [root / ".venv/bin/python", Path(sys.executable),
                      Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"]
        configured = os.environ.get("STUDY_ATLAS_PDF_PYTHON")
        if configured:
            candidates.insert(0, Path(configured))
        for executable in dict.fromkeys(candidates):
            if not executable.is_file():
                continue
            check = subprocess.run([str(executable), "-c", "import reportlab" + (",pypdfium2" if kind == "freeform" else "")], capture_output=True, timeout=15)
            if check.returncode:
                continue
            result = subprocess.run([str(executable), str(root / "pdf_export.py"), "--worker", kind],
                                    input=json.dumps(payload, ensure_ascii=False).encode(), capture_output=True, timeout=150)
            if result.returncode:
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
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, PageBreak, NextPageTemplate, KeepTogether, Flowable

    fonts = [os.environ.get("STUDY_ATLAS_PDF_FONT", ""), "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
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

    def decorate(canvas, document, writing=False):
        canvas.saveState()
        canvas.setFont("StudyChinese", 10)
        canvas.setFillColor(green)
        canvas.drawString(left, height - 32, "学习图谱 / AI 学习笔记")
        canvas.setStrokeColor(colors.HexColor("#dbe4d6"))
        canvas.line(left, height - 42, width - 38, height - 42)
        if not writing:
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
        else:
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
        PageTemplate(id="notes", frames=[Frame(left, bottom, body_width, top - bottom, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=decorate),
        PageTemplate(id="writing", frames=[Frame(left, bottom, width - 76, top - bottom, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=lambda c, d: decorate(c, d, True))])
    base = dict(fontName="StudyChinese", textColor=ink, wordWrap="CJK", splitLongWords=True, alignment=TA_LEFT)
    styles = {
        "title": ParagraphStyle("title", fontSize=19, leading=27, spaceAfter=15, **base),
        "h1": ParagraphStyle("h1", fontSize=15, leading=23, spaceBefore=12, spaceAfter=8, keepWithNext=True, **base),
        "h2": ParagraphStyle("h2", fontSize=12, leading=20, spaceBefore=13, spaceAfter=7, keepWithNext=True, **base),
        "text": ParagraphStyle("text", fontSize=10.5, leading=19, spaceAfter=7, **base),
        "meta": ParagraphStyle("meta", fontSize=8.5, leading=14, spaceAfter=7, fontName="StudyChinese", textColor=muted, wordWrap="CJK", splitLongWords=True)}

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
    for index, video in enumerate(payload["videos"]):
        if story:
            story.append(PageBreak())
        title = video.get("aiTitle") or video["title"]
        story.append(Paragraph(rich(title), styles["title"]))
        story.append(Paragraph(rich(category_name(video["categoryId"])) + " · " + rich(video["author"] or "作者未填写"), styles["meta"]))
        story.append(Paragraph('视频来源 [S1]：<a href="' + escape(video["url"], quote=True) + '">打开原视频</a>', styles["meta"]))
        if video.get("aiTitle") and video["aiTitle"] != video["title"]:
            story.append(Paragraph("原始标题：" + rich(video["title"]), styles["meta"]))
        paragraphs(video.get("summary", "") or "尚无总结，以下为已保存的补充笔记。")
        knowledge = video.get("knowledge")
        if knowledge:
            story.extend([PageBreak(), Paragraph("知识脑图", styles["title"]), Paragraph(rich(knowledge["overview"]), styles["meta"]), BrainDiagram(knowledge), PageBreak(), Paragraph("详尽知识模块", styles["title"])])
            for module in knowledge["modules"]:
                story.append(Paragraph(rich(module["title"]), styles["h1"]))
                story.append(Paragraph("学习目标：" + rich(module["objective"]), styles["meta"]))
                if module["prerequisites"]:
                    story.append(Paragraph("前置知识：" + rich("、".join(module["prerequisites"])), styles["meta"]))
                paragraphs(module["notes"])
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
    for insight in payload["insights"]:
        if story:
            story.append(PageBreak())
        story.append(Paragraph(rich(insight["title"]), styles["title"]))
        paragraphs(insight["content"])
        for source in insight["sources"]:
            story.append(Paragraph('[' + rich(source["source"]) + '] <a href="' + escape(source["url"], quote=True) + '">' + rich(source["title"]) + '</a>', styles["meta"]))
    story.extend([NextPageTemplate("writing"), PageBreak(), Paragraph("我的理解与练习", styles["title"]), Paragraph("在无边记里添加手写、箭头和自己的例子；AI 原稿与个人批注分开保留。", styles["meta"])])
    doc.build(story)
    return result.getvalue()


def make_freeform(pdf):
    import pypdfium2 as pdfium
    bundle = io.BytesIO()
    document = pdfium.PdfDocument(pdf)
    try:
        if len(document) > 60:
            raise ValueError("Export individual courses to limit image memory")
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("AI学习笔记.pdf", pdf)
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
            archive.writestr("使用说明.txt", "学习图谱 · 无边记素材\n\n1. 用 AirDrop 或自行保管的 iCloud 云盘把此文件传到 iPad。\n2. 在“文件”中轻点 ZIP 解压，打开“图片”文件夹。\n3. 在无边记新建看板，通过分屏拖入所需 PNG 图片；也可插入 PDF 作为原稿附件。\n4. 在画布上添加手写、文本框和连线。PNG 是图片，文字不能直接编辑；PDF 保留可选中的文字。\n5. 看板与批注由无边记管理，不会自动回写学习图谱；如需归档，可从无边记导出带批注的 PDF。\n\nAI 原稿与个人批注请分别保存，不要把个人素材提交到公开 GitHub。\n".encode("utf-8"))
    finally:
        document.close()
    return bundle.getvalue()


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--worker":
    data = json.load(sys.stdin)
    pdf = make_pdf(data)
    sys.stdout.buffer.write(make_freeform(pdf) if sys.argv[2] == "freeform" else pdf)
