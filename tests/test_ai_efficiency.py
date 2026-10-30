"""无损压紧、缓存隔离、增量翻译与独立自查；不调用真实模型。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from ai_efficiency import compact_json, validated_request, efficiency_status, record_model_call
from integrations import Integrations, IntegrationError, prepare_material
from knowledge import build_knowledge
from note_translations import translate_notes
from server import LibraryStore
import test_knowledge as knowledge_fixture
from test_translations import TranslationAI
from test_practice import fixture


class EfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); self.ai = Integrations(self.root)
    def tearDown(self): self.tmp.cleanup()
    def test_compact_json_round_trip_keeps_code_quotes_and_all_fields(self):
        value = {'代码': '  if (x) {\n    printf("你好");\n  }', '字幕': ['a  b', '重复', '重复'], 'end': '尾段'}
        compact = compact_json(value)
        self.assertEqual(json.loads(compact), value)
        self.assertLess(len(compact), len(json.dumps(value, ensure_ascii=False)))
    def test_validated_hit_no_provider_call_and_private_cache(self):
        calls = []
        def generate(prompt): calls.append(prompt); return {'content': '{"完整笔记":"保留正文"}', 'sessionId': 'private-session'}
        validate = lambda r: json.loads(r['content'])
        first = validated_request(self.ai, generate, '原始资料', validate, 'test')
        second = validated_request(self.ai, generate, '原始资料', validate, 'test')
        self.assertEqual(first, second); self.assertEqual(len(calls), 1)
        stats = efficiency_status(self.ai); self.assertEqual(stats['cacheHits'], 1)
        self.assertEqual(stats['avoidedInputCharacters'], len('原始资料'))
        p = next(self.ai.local.glob('ai-cache-*.json')); self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('private-session', p.read_text())
    def test_model_source_task_and_setting_isolate_cache(self):
        calls = []
        def generate(prompt): calls.append(prompt); return {'content': '{}'}
        validate = lambda r: json.loads(r['content'])
        def run(prompt='A', task='x'): return validated_request(self.ai, generate, prompt, validate, task)
        run(); run(); run('B'); run(task='y')
        self.ai.write('ai', {'mode':'deepseek','model':'other'}); run()
        self.ai.write('ai', {'mode':'deepseek','model':'other','smartCache':False}); run(); run()
        self.assertEqual(len(calls), 6)
    def test_invalid_or_failed_responses_never_cached_or_retried(self):
        calls = []
        def bad(prompt): calls.append(prompt); return {'content': 'invalid json'}
        for _ in range(2):
            with self.assertRaises(ValueError): validated_request(self.ai, bad, 'A', lambda r: json.loads(r['content']), 'bad')
        self.assertEqual(len(calls), 2); self.assertFalse(list(self.ai.local.glob('ai-cache-*.json')))
        def fail(prompt): raise IntegrationError('网络断线')
        with self.assertRaises(IntegrationError): validated_request(self.ai, fail, 'A', lambda r:r, 'network')
    def test_long_material_reuses_unchanged_chunks_and_keeps_tail(self):
        calls = []
        def generate(prompt): calls.append(prompt); return {'content': prompt.split('资料：\n')[-1][-30:]}
        source = '甲' * 80000 + '乙' * 79990 + '尾部独有结论'
        before = prepare_material(source, generate, engine=self.ai)
        self.assertEqual(before, prepare_material(source, generate, engine=self.ai)); self.assertEqual(len(calls), 2)
        changed = source[:-1] + '新'
        self.assertIn('尾部独有结新', prepare_material(changed, generate, engine=self.ai))
        self.assertEqual(len(calls), 3)
    def test_actual_usage_is_separate_from_character_savings(self):
        record_model_call(self.ai, '中文prompt', {'usage': {'prompt_tokens': 12, 'completion_tokens': 8}})
        record_model_call(self.ai, 'no usage', {})
        stats = efficiency_status(self.ai)
        self.assertEqual(stats['modelCalls'], 2); self.assertEqual(stats['usageReports'], 1)
        self.assertEqual((stats['promptTokens'], stats['completionTokens']), (12, 8))
    def test_only_changed_translation_module_calls_model(self):
        data = fixture(); second = copy.deepcopy(data['videos'][0]['knowledge']['modules'][0]); second['id'] = 'm2'
        data['videos'][0]['knowledge']['modules'].append(second)
        path = self.root/'library.json'; path.write_text(json.dumps(data)); store = LibraryStore(path); ai = TranslationAI()
        first = translate_notes(store, ai, 'v1', 'en', lambda m: None); self.assertEqual(len(ai.calls), 3)
        data = store.read(); data['videos'][0]['knowledge']['modules'][1]['notes'] += ' 只改这一段'; store.save(data)
        result = translate_notes(store, ai, 'v1', 'en', lambda m: None)
        self.assertEqual(len(ai.calls), 4); self.assertEqual(result['modules'][0], first['modules'][0])
        data = store.read(); data['videos'][0]['summary'] += ' 只改概览'; store.save(data)
        translate_notes(store, ai, 'v1', 'en', lambda m: None); self.assertEqual(len(ai.calls), 5)
    def test_rebuilding_reuses_details_but_runs_fresh_independent_review(self):
        case = knowledge_fixture.KnowledgeTests(); case.setUp()
        try:
            before = case.build(); case.ai.calls = []
            after = case.build()
            self.assertEqual(before['modules'], after['modules'])
            self.assertEqual(len(case.ai.calls), 2)  # 短大纲 + 独立复核，两个详尽正文不重写。
            self.assertIn('独立的第二轮自查', case.ai.calls[-1])
        finally: case.tearDown()
