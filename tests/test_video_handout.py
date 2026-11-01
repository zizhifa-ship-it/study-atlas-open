"""完整视频讲义：时间轴、章节、PDF 与无边记素材的边界测试。"""
import copy
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from integrations import IntegrationError
from pdf_export import export_notes, make_freeform, make_pdf, select_notes
from server import validate_library
from test_practice import fixture
from transcript_sources import cached_timing, normalize_chapters, parse_timed_transcript

TEXT_1 = '第一句内容，说明这个概念解决什么问题，并给出课程中的例子。'
TEXT_2 = '第二句内容，完整保留后半段，并补充适用条件和易错点。'
URL = 'https://www.youtube.com/watch?v=abcdefghijk'


def handout_library():
    library = copy.deepcopy(fixture())
    video = library['videos'][0]
    video['url'] = URL
    video['durationSec'] = 125
    video['aiTitle'] = '测试视频讲义'
    video['transcript'] = TEXT_1 + '\n' + TEXT_2
    video['transcriptInfo'] = {
        'kind': 'captions', 'source': 'YouTube 原语言字幕', 'language': 'zh',
        'createdAt': '2026-11-01T00:00:00+00:00',
        'timeline': [0, 12],
        'chapters': [{'start': 0, 'title': '开场'}, {'start': 12, 'title': '核心'}],
    }
    return library


class TimedTranscriptTests(unittest.TestCase):
    def test_json3_and_vtt_keep_line_aligned_timestamps(self):
        json3 = json.dumps({'events': [
            {'tStartMs': 0, 'segs': [{'utf8': TEXT_1}]},
            {'tStartMs': 12500, 'segs': [{'utf8': TEXT_2}]},
        ]}, ensure_ascii=False)
        text, timeline = parse_timed_transcript(json3, 'json3')
        self.assertEqual(text.splitlines(), [TEXT_1, TEXT_2])
        self.assertEqual(timeline, [0, 12])
        vtt = 'WEBVTT\n\n1\n00:00:00.000 --> 00:00:10.000\n%s\n\n2\n00:00:12.500 --> 00:00:20.000\n%s\n' % (TEXT_1, TEXT_2)
        text, timeline = parse_timed_transcript(vtt, 'vtt')
        self.assertEqual(text.splitlines(), [TEXT_1, TEXT_2])
        self.assertEqual(timeline, [0, 12])

    def test_chapters_are_sorted_and_deduplicated(self):
        chapters = normalize_chapters([
            {'start_time': 12.5, 'title': '核心'},
            {'start_time': 0, 'title': '开场'},
            {'start_time': 12, 'title': '重复时间'},
        ], 125)
        self.assertEqual(chapters, [{'start': 0, 'title': '开场'}, {'start': 12, 'title': '核心'}])

    def test_legacy_segment_cache_can_supply_timing_without_refetching(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / '.local/transcripts'
            folder.mkdir(parents=True)
            (folder / 'abcdefghijk.json').write_text(json.dumps({
                'transcript': TEXT_1 + '\n' + TEXT_2,
                'segments': [{'start': 0, 'text': TEXT_1}, {'start': 12.2, 'text': TEXT_2}],
            }, ensure_ascii=False), encoding='utf-8')
            timeline, chapters = cached_timing(root, URL, TEXT_1 + '\n' + TEXT_2)
        self.assertEqual(timeline, [0, 12])
        self.assertEqual(chapters, [])

    def test_validation_keeps_timing_only_when_lines_align(self):
        library = handout_library()
        clean = validate_library(library)
        info = clean['videos'][0]['transcriptInfo']
        self.assertEqual(info['timeline'], [0, 12])
        self.assertEqual(info['chapters'], [{'start': 0, 'title': '开场'}, {'start': 12, 'title': '核心'}])
        changed = copy.deepcopy(library)
        changed['videos'][0]['transcript'] = '这是一行不同的字幕，长度足够但不再对应旧时间点。'
        clean = validate_library(changed)
        self.assertNotIn('timeline', clean['videos'][0]['transcriptInfo'])


class PayloadTests(unittest.TestCase):
    def test_default_export_still_excludes_transcript(self):
        selected = select_notes(handout_library(), 'v1')
        self.assertFalse(selected['handout'])
        self.assertNotIn('transcript', selected['videos'][0])

    def test_full_handout_payload_includes_transcript_and_metadata(self):
        selected = select_notes(handout_library(), 'v1', include_transcript=True)
        self.assertTrue(selected['handout'])
        self.assertEqual(selected['videos'][0]['transcript'], TEXT_1 + '\n' + TEXT_2)
        self.assertEqual(selected['videos'][0]['transcriptInfo']['timeline'], [0, 12])
        self.assertNotIn('apiKey', selected)

    def test_full_handout_requires_a_single_course(self):
        with self.assertRaises(IntegrationError):
            export_notes(handout_library(), '', 'handout')


@unittest.skipUnless(
    importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdfium2')
    and importlib.util.find_spec('pypdf') and Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf').exists(),
    'PDF 依赖或测试中文字体未安装',
)
class HandoutPDFTests(unittest.TestCase):
    def test_handout_contains_cover_chapters_timeline_and_complete_transcript(self):
        from pypdf import PdfReader
        payload = select_notes(handout_library(), 'v1', include_transcript=True)
        pdf = make_pdf(payload)
        reader = PdfReader(io.BytesIO(pdf))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        for expected in ['完整视频讲义', '章节目录', '完整字幕', '开场', '核心', '生成日期', '完整内容到此结束']:
            self.assertIn(expected, text)
        self.assertIn(TEXT_1, text)
        self.assertIn('第二句内容', text)
        links = [annotation.get_object().get('/A', {}).get('/URI')
                 for page in reader.pages for annotation in page.get('/Annots', [])]
        self.assertIn(URL + '&t=0', links)
        self.assertIn(URL + '&t=12', links)
        with zipfile.ZipFile(io.BytesIO(make_freeform(pdf, payload))) as archive:
            names = archive.namelist()
            self.assertIn('完整视频讲义.pdf', names)
            self.assertIn('完整视频讲义.md', names)
            self.assertEqual(len([name for name in names if name.endswith('.png')]), len(reader.pages))
            markdown = archive.read('完整视频讲义.md').decode('utf-8')
            self.assertIn('## 章节目录', markdown)
            self.assertIn('## 完整字幕', markdown)
            self.assertIn(TEXT_2, markdown)


if __name__ == '__main__':
    unittest.main()
