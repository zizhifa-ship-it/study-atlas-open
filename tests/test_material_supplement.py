"""Local long-video supplements: append, de-duplicate, replace and scope."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from importer import AutoImporter
from integrations import IntegrationError
from server import LibraryStore

SOURCE = '网络课程原文：IP 用于寻址，DHCP 自动分配地址，TCP 提供确认与重传。' * 2
SUPPLEMENT = '补充讲义：子网掩码用于划分网络与主机部分，路由表决定下一跳。'


def video(vid='video'):
    return {
        'id': vid, 'title': '网络课程', 'url': 'https://example.com/lesson',
        'categoryId': 'net', 'author': '', 'durationSec': 0, 'tags': [],
        'status': 'todo', 'favorite': False, 'summary': '已有总结。[S1]',
        'transcript': SOURCE, 'notes': [], 'createdAt': '2026-10-27',
        'updatedAt': '2026-10-27',
    }


class LocalOnlyAI:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = 0

    def read(self, name):
        return {}

    def harness_generate(self, prompt):
        self.calls += 1
        raise AssertionError('save/duplicate supplements must not call the model')


class SupplementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'library.json'
        self.path.write_text(json.dumps({
            'schemaVersion': 1, 'revision': 0,
            'categories': [{'id': 'net', 'name': '网络基础', 'parentId': None, 'color': 'green', 'description': ''}],
            'videos': [video()], 'insights': [],
        }, ensure_ascii=False), encoding='utf-8')
        self.store = LibraryStore(self.path)
        self.ai = LocalOnlyAI()
        self.importer = AutoImporter(self.store, self.ai)

    def tearDown(self):
        self.importer.queue.join()
        self.temp.cleanup()

    def test_append_is_local_and_duplicate_never_calls_ai(self):
        result = self.importer.submit_supplement({
            'videoId': 'video', 'filename': 'chapter-2.md', 'content': SUPPLEMENT,
            'mode': 'append', 'task': 'save',
        })
        self.assertFalse(result['queued'])
        self.assertGreater(result['addedCharacters'], 0)
        saved = self.store.read()['videos'][0]
        self.assertTrue(saved['transcript'].startswith(SOURCE))
        self.assertIn('[补充资料：chapter-2.md]', saved['transcript'])
        self.assertIn(SUPPLEMENT, saved['transcript'])
        self.assertEqual(saved['transcriptInfo']['materials'][0]['filename'], 'chapter-2.md')
        self.assertEqual(self.ai.calls, 0)

        repeat = self.importer.submit_supplement({
            'videoId': 'video', 'filename': 'chapter-2.md', 'content': SUPPLEMENT,
            'mode': 'append', 'task': 'save',
        })
        self.assertTrue(repeat['duplicate'])
        self.assertEqual(repeat['addedCharacters'], 0)
        self.assertEqual(self.store.read()['videos'][0]['transcript'], saved['transcript'])
        self.assertEqual(len(self.store.read()['videos'][0]['transcriptInfo']['materials']), 1)
        self.assertEqual(self.ai.calls, 0)

    def test_replace_changes_source_and_resets_supplement_list(self):
        first = self.importer.submit_supplement({
            'videoId': 'video', 'filename': 'first.md', 'content': SUPPLEMENT,
            'mode': 'append', 'task': 'save',
        })
        self.assertGreater(first['addedCharacters'], 0)
        result = self.importer.submit_supplement({
            'videoId': 'video', 'filename': 'replacement.md',
            'content': '替换后的完整讲义，包含路由、DNS 与故障排查的详细说明。',
            'mode': 'replace', 'task': 'save',
        })
        saved = self.store.read()['videos'][0]
        self.assertEqual(saved['transcript'], '替换后的完整讲义，包含路由、DNS 与故障排查的详细说明。')
        self.assertEqual([m['filename'] for m in saved['transcriptInfo']['materials']], ['replacement.md'])
        self.assertNotIn(SOURCE, saved['transcript'])

    def test_combined_material_over_limit_does_not_overwrite(self):
        data = self.store.read()
        data['videos'][0]['transcript'] = 'A' * 2999980
        self.store.save(data)
        before = self.store.read()['videos'][0]['transcript']
        with self.assertRaisesRegex(IntegrationError, '300 万'):
            self.importer.submit_supplement({
                'videoId': 'video', 'filename': 'too-long.md',
                'content': SUPPLEMENT, 'mode': 'append', 'task': 'save',
            })
        self.assertEqual(self.store.read()['videos'][0]['transcript'], before)

    def test_knowledge_scope_queues_without_rewriting_summary(self):
        with patch.object(self.importer, 'submit_knowledge', return_value={
            'videoId': 'video', 'library': self.store.read(), 'duplicate': False,
        }) as submit:
            result = self.importer.submit_supplement({
                'videoId': 'video', 'filename': 'chapter.md', 'content': SUPPLEMENT,
                'mode': 'append', 'task': 'knowledge',
            })
        self.assertTrue(result['queued'])
        submit.assert_called_once_with('video')
        self.assertEqual(result['task'], 'knowledge')

    def test_full_scope_on_manual_platform_routes_to_knowledge_without_fetching(self):
        with patch.object(self.importer, 'submit_knowledge', return_value={
            'videoId': 'video', 'library': self.store.read(), 'duplicate': False,
        }) as knowledge, patch.object(self.importer, 'submit') as fetch:
            result = self.importer.submit_supplement({
                'videoId': 'video', 'filename': 'manual.md', 'content': SUPPLEMENT,
                'mode': 'append', 'task': 'full',
            })
        self.assertTrue(result['queued'])
        knowledge.assert_called_once_with('video')
        fetch.assert_not_called()

    def test_active_task_saves_for_later_without_queueing(self):
        data = self.store.read()
        data['videos'][0]['automation'] = {'status': 'ai', 'message': '正在整理'}
        self.store.save(data)
        with patch.object(self.importer, 'submit') as submit:
            result = self.importer.submit_supplement({
                'videoId': 'video', 'filename': 'late.md', 'content': SUPPLEMENT,
                'mode': 'append', 'task': 'full',
            })
        self.assertFalse(result['queued'])
        self.assertTrue(result['active'])
        self.assertIn('整理任务', result['message'])
        submit.assert_not_called()
        self.assertIn(SUPPLEMENT, self.store.read()['videos'][0]['transcript'])


if __name__ == '__main__':
    unittest.main()
