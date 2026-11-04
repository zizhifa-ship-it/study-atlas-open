"""Real PDF extraction and bounded long-source recovery, with no paid AI calls."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from integrations import IntegrationError, Integrations, prepare_material, split_material
from materials import parse_material
from pdf_import import extract_pdf, read_pdf_upload, IMPORT_LOCK
from transcript_sources import parse_transcript


def pdf_data(pages=2, blank=False):
    from reportlab.pdfgen.canvas import Canvas
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    for n in range(pages):
        if not blank:
            canvas.drawString(50, 700, 'Lesson %d: IP addressing, routing and network practice.' % (n + 1))
        canvas.showPage()
    canvas.save()
    return {'filename': 'network.PDF', 'base64': base64.b64encode(buffer.getvalue()).decode()}


try:
    import reportlab, pypdfium2
    PDF_READY = True
except ImportError:
    PDF_READY = False


@unittest.skipUnless(PDF_READY, 'optional PDF dependencies not installed')
class PDFTests(unittest.TestCase):
    def test_pdf_pages_and_end_are_extracted_and_can_be_saved(self):
        result = extract_pdf(pdf_data())
        self.assertEqual(result['pages'], 2)
        self.assertIn('[PDF 第 2 页]', result['content'])
        self.assertIn('Lesson 2:', result['content'])
        self.assertEqual(result['filename'], 'network.md')
        _, _, text = parse_material(dict(result, title='网络课程'))
        self.assertEqual(text, result['content'])

    def test_worker_extracts_without_writing_original_pdf(self):
        result = read_pdf_upload(pdf_data())
        self.assertIn('Lesson 2:', result['content'])
        self.assertFalse(IMPORT_LOCK.locked())

    def test_scans_and_malformed_inputs_cannot_become_fake_notes(self):
        for data in [pdf_data(blank=True), {'filename': 'a.pdf', 'base64': '%%%bad'},
                     {'filename': 'a.exe', 'base64': ''}, {'filename': 'a.pdf', 'base64': base64.b64encode(b'not PDF').decode()}]:
            with self.assertRaises(IntegrationError): extract_pdf(data)

    def test_page_cap_and_mixed_empty_pages_are_explicit(self):
        with patch('pdf_import.MAX_PAGES', 1):
            with self.assertRaisesRegex(IntegrationError, '300'): extract_pdf(pdf_data())
        from reportlab.pdfgen.canvas import Canvas
        buffer = io.BytesIO(); canvas = Canvas(buffer)
        canvas.drawString(50, 700, 'Sufficient real content about network routing and addressing.')
        canvas.showPage(); canvas.showPage(); canvas.save()
        result = extract_pdf({'filename': 'mixed.pdf', 'base64': base64.b64encode(buffer.getvalue()).decode()})
        self.assertEqual(result['emptyPages'], [2]); self.assertIn('OCR', result['warning'])

    def test_worker_timeout_releases_lock(self):
        import subprocess
        with patch('pdf_import.subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 60)):
            with self.assertRaisesRegex(IntegrationError, '超时'): read_pdf_upload(pdf_data())
        self.assertFalse(IMPORT_LOCK.locked())


class LongSourceTests(unittest.TestCase):
    def test_split_is_lossless_including_paragraph_boundaries(self):
        source = ('first paragraph\n' * 1050) + 'FINAL_TAIL'
        chunks = split_material(source, 6000)
        self.assertEqual(''.join(c for _, c in chunks), source)
        self.assertTrue(all(0 < len(c) <= 6000 for _, c in chunks))
        self.assertTrue(chunks[-1][1].endswith('FINAL_TAIL'))

    def test_long_original_and_material_preserve_more_than_old_limit(self):
        source = 'network address\n' * 20000 + 'END_OF_COURSE'
        self.assertEqual(parse_transcript(source).splitlines()[-1], 'END_OF_COURSE')
        self.assertTrue(parse_material({'title': 'Full course', 'filename': 'lecture.md', 'content': source})[2].endswith('END_OF_COURSE'))
        with self.assertRaises(IntegrationError):
            parse_material({'title': 'Too long', 'filename': 'large.md', 'content': 'x' * 800001})

    def test_hierarchy_keeps_all_source_and_bounds_each_call(self):
        calls = []
        def model(prompt):
            calls.append(prompt)
            return {'content': '摘要' * 1700}
        source = 'A' * 50000 + 'TAIL'
        result = prepare_material(source, model)
        self.assertIn('50004', result)
        self.assertLess(len(result), 12500)
        self.assertTrue(all(len(p) < 12500 for p in calls))
        first_pass = [p.split('资料：\n', 1)[1] for p in calls if '第 1 层' in p]
        self.assertEqual(''.join(first_pass), source)
        self.assertTrue(any('第 2 层' in p for p in calls))

    def test_resume_reuses_completed_segments_after_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            ai = Integrations(Path(folder)); calls = []
            def model(prompt):
                calls.append(prompt)
                if len(calls) == 2: raise IntegrationError('connection interrupted')
                return {'content': prompt.split('资料：\n')[1][-30:]}
            source = 'A' * 12000 + 'B' * 12000 + 'TAIL'
            with self.assertRaises(IntegrationError): prepare_material(source, model, engine=ai)
            result = prepare_material(source, model, engine=ai)
            self.assertEqual(len(calls), 4)
            self.assertIn('TAIL', result)

    def test_local_models_use_smaller_chunks(self):
        with tempfile.TemporaryDirectory() as folder:
            ai = Integrations(Path(folder)); ai.write('ai', {'mode': 'compatible', 'compatibleProvider': 'ollama'})
            calls = []
            def model(prompt): calls.append(prompt); return {'content': 'source-backed summary'}
            prepare_material('X' * 12001, model, engine=ai)
            self.assertEqual(len(calls), 3)
            self.assertTrue(all(len(p.split('资料：\n')[1]) <= 6000 for p in calls))
