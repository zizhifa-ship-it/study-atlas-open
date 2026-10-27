"""AI 自动保存与 iPad 导出的边界，不读取个人资料。"""
import copy
import importlib.util
import io
import unittest
import zipfile
from pathlib import Path
from integrations import prepare_material, IntegrationError
from note_results import apply_ai_summary
from pdf_export import select_notes, make_pdf, make_freeform


class NotesTests(unittest.TestCase):
    def test_ai_replaces_summary_and_keeps_previous_version(self):
        target={"summary":"旧总结", "notes":[]}
        apply_ai_summary(target,"新知识总结 [S1]","测试模型","旧总结")
        self.assertEqual(target["summary"],"新知识总结 [S1]")
        self.assertIn("旧总结",target["notes"][0]["text"])
        apply_ai_summary(target,"新知识总结 [S1]","测试模型","新知识总结 [S1]")
        self.assertEqual(len(target["notes"]),1)
    def test_concurrent_manual_edits_keep_ai_result_as_separate_note(self):
        target={"summary":"人工刚写的总结", "notes":[]}
        apply_ai_summary(target,"AI 新整理内容 [S1]","测试模型","原始总结")
        self.assertEqual(target["summary"],"人工刚写的总结")
        self.assertIn("AI 新整理内容",target["notes"][0]["text"])
    def test_long_material_keeps_last_segment(self):
        seen=[]
        def model(prompt):
            seen.append(prompt)
            return {"content":"本段要点"}
        text="前段资料" * 24000 + "仅尾部出现的重要结论"
        combined=prepare_material(text,model)
        self.assertEqual(len(seen),2)
        self.assertIn("仅尾部出现的重要结论",seen[-1])
        self.assertIn(str(len(text)),combined)
    def test_export_payload_excludes_transcript_and_credentials(self):
        library=fixture()
        library["videos"][0]["transcript"]="private transcript"
        library["apiKey"]="private key"
        selected=select_notes(library)
        self.assertNotIn("transcript",selected["videos"][0])
        self.assertNotIn("apiKey",selected)
        with self.assertRaises(IntegrationError):select_notes(library,"missing")


def fixture():
    return {"categories":[{"id":"net","name":"网络基础","parentId":None}],"videos":[
        {"id":"one","title":"Original Course","aiTitle":"网络协议与诊断","author":"示例讲师","url":"https://example.com/course","categoryId":"net","summary":"# 学习重点\n\n## 核心概念\nIP 负责寻址，端口定位应用。[S1]\n\n- ICMP 用于诊断。\n- **先复现再定位**。\n\n## 复习问题\n为什么网络可达不代表应用可用？","notes":[{"id":"n","timeSec":20,"text":"我的批注：先检查网关。","createdAt":"2026-10-27"}]}],"insights":[]}


@unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdfium2') and importlib.util.find_spec('pypdf') and Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf').exists(),"PDF 依赖或测试中文字体未安装")
class PDFTests(unittest.TestCase):
    def test_pdf_contains_selectable_chinese_source_and_writing_page(self):
        from pypdf import PdfReader
        pdf=make_pdf(select_notes(fixture()))
        reader=PdfReader(io.BytesIO(pdf))
        self.assertGreaterEqual(len(reader.pages),2)
        text="\n".join(p.extract_text() for p in reader.pages)
        self.assertIn("网络协议与诊断",text)
        self.assertIn("我的理解与练习",text)
        self.assertIn("IP 负责寻址",text)
        self.assertNotIn("private",text)
        links=[a.get_object().get('/A',{}).get('/URI') for p in reader.pages for a in p.get('/Annots',[])]
        self.assertIn('https://example.com/course',links)
        with zipfile.ZipFile(io.BytesIO(make_freeform(pdf))) as z:
            images=[n for n in z.namelist() if n.endswith('.png')]
            self.assertEqual(len(images),len(reader.pages))
            self.assertEqual(z.read('AI学习笔记.pdf'),pdf)
            self.assertTrue(z.read(images[0]).startswith(b'\x89PNG'))
