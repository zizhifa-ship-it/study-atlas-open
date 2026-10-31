"""任务摘要、进度隔离和真正的中断恢复；不调用外部服务。"""
import copy
import hashlib
import json
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from ai_efficiency import model_identity
from importer import AutoImporter
from integrations import IntegrationError
from knowledge import build_knowledge, material_hash
from server import LibraryStore, make_handler
from tasks import checkpoint_summary, task_snapshot, recovery_mode
from test_practice import fixture
from test_knowledge import FakeKnowledgeAI


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'library.json'
        self.data=fixture();self.path.write_text(json.dumps(self.data,ensure_ascii=False))
        self.store=LibraryStore(self.path);self.ai=FakeKnowledgeAI();self.importer=None
        self.name='knowledge-job-'+hashlib.sha256(b'v1').hexdigest()[:24]
    def tearDown(self):
        if self.importer:self.importer.queue.join()
        self.tmp.cleanup()
    def checkpoint(self):
        return {'version':3,'fingerprint':material_hash(self.data['videos'][0]),'modelKey':model_identity(self.ai),
                'mode':'build','material':'PRIVATE-MATERIAL','plan':{'modules':[{},{}]},'modules':[{}], 'reports':[]}
    def test_snapshot_reports_real_counts_and_never_exposes_source_or_config(self):
        self.data['videos'][0]['automation']={'status':'failed','message':'网络断开','task':'detailed'};self.store.save(self.data)
        self.ai.write(self.name,self.checkpoint())
        q=queue.Queue();q.put(('v1','detailed'))
        importer=SimpleNamespace(lock=threading.Lock(),queue=q,store=self.store,integrations=self.ai,running=None)
        result=task_snapshot(importer);item=result['items'][0]
        self.assertEqual(result['counts']['attention'],1);self.assertEqual(item['queuePosition'],1)
        self.assertEqual((item['checkpoint']['modulesDone'],item['checkpoint']['modulesTotal']),(1,2))
        text=json.dumps(result);self.assertNotIn('PRIVATE-MATERIAL',text);self.assertNotIn(self.data['videos'][0]['transcript'],text)
        self.assertNotIn('modelKey',text);self.assertNotIn('cookies',text)
    def test_source_model_and_legacy_checkpoints_are_distinguished(self):
        job=self.checkpoint();self.ai.write(self.name,job)
        self.assertTrue(checkpoint_summary(self.ai,self.data['videos'][0])['available'])
        changed=copy.deepcopy(self.data['videos'][0]);changed['transcript']+='新资料'
        self.assertEqual(checkpoint_summary(self.ai,changed)['reason'],'source_changed')
        job['modelKey']=['different'];self.ai.write(self.name,job)
        self.assertEqual(checkpoint_summary(self.ai,self.data['videos'][0])['reason'],'model_changed')
        job['version']=2;self.ai.write(self.name,job)
        self.assertEqual(checkpoint_summary(self.ai,self.data['videos'][0])['reason'],'legacy')
    def test_resume_keeps_completed_module_and_skips_metadata_captions_and_summary(self):
        generate=self.ai.harness_generate
        def fail_second(prompt):
            if '指定模块' in prompt and json.loads(prompt.split('资料：\n')[-1])['module']['id']=='m2':
                raise IntegrationError('模拟断线')
            return generate(prompt)
        self.ai.harness_generate=fail_second
        with self.assertRaises(IntegrationError):build_knowledge(self.store,self.ai,'v1',lambda message:None)
        self.data=self.store.read();old_summary=self.data['videos'][0]['summary'];old_notes=self.data['videos'][0]['notes']
        self.data['videos'][0]['automation']={'status':'failed','message':'模拟断线','task':'detailed'};self.store.save(self.data)
        self.ai.harness_generate=generate;self.ai.calls=[];self.importer=AutoImporter(self.store,self.ai)
        with patch('importer.metadata',side_effect=AssertionError('不应再次获取元数据')):
            self.importer.resume('v1');self.importer.queue.join()
        result=self.store.read()['videos'][0]
        self.assertEqual(len(self.ai.calls),2) # 第二模块和独立自查；没有重新规划或重写第一模块。
        self.assertEqual(len(result['knowledge']['modules']),2)
        self.assertEqual(result['summary'],old_summary);self.assertEqual(result['notes'],old_notes)
        self.assertEqual(result['automation']['status'],'ready');self.assertEqual(result['automation']['task'],'detailed')
    def test_translation_recovery_remembers_language(self):
        self.data['videos'][0]['automation']={'status':'failed','message':'中断','task':'translate:en'};self.store.save(self.data)
        self.importer=AutoImporter(self.store,self.ai)
        with patch('importer.translate_notes') as translate:
            self.importer.resume('v1');self.importer.queue.join()
        self.assertEqual(translate.call_args.args[3],'en')
    def test_resume_preserves_basic_import_and_manual_module_scope(self):
        video=copy.deepcopy(self.data['videos'][0]);video['summary']=''
        video['automation']={'status':'failed','task':'knowledge'}
        self.assertEqual(recovery_mode(self.ai,video),'knowledge')
        video['automation']['task']='import'
        self.assertEqual(recovery_mode(self.ai,video),'saved-import')
        video['transcript']=''
        self.assertEqual(recovery_mode(self.ai,video),'import')
    def test_restart_retains_task_type_and_does_not_call_ai(self):
        self.data['videos'][0]['automation']={'status':'ai','message':'处理中','task':'review'};self.store.save(self.data)
        self.importer=AutoImporter(self.store,self.ai)
        self.assertEqual(self.store.read()['videos'][0]['automation']['task'],'review')
        self.assertEqual(self.store.read()['videos'][0]['automation']['status'],'failed')
        self.assertEqual(self.ai.calls,[])
    def test_resume_cannot_duplicate_running_task_or_restart_completed_course(self):
        self.data['videos'][0]['automation']={'status':'queued','message':'等待','task':'knowledge'};self.store.save(self.data)
        # 不启动 worker，模拟尚未处理的队列，验证重复提交不增加任务。
        importer=AutoImporter.__new__(AutoImporter);importer.lock=threading.Lock();importer.store=self.store;importer.integrations=self.ai;importer.queue=queue.Queue()
        self.assertTrue(importer.resume('v1')['duplicate']);self.assertTrue(importer.queue.empty())
        data=self.store.read();data['videos'][0]['automation']={'status':'ready','message':'完成'};self.store.save(data)
        with self.assertRaises(IntegrationError):importer.resume('v1')
        with self.assertRaises(IntegrationError):importer.resume('missing')
    def test_tasks_http_is_read_only_and_external_origin_is_rejected(self):
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        before=self.path.read_bytes();server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.store,self.ai))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with urlopen(base+'/api/tasks') as response:self.assertIn('counts',json.load(response))
            with self.assertRaises(HTTPError) as error:urlopen(Request(base+'/api/tasks',headers={'Origin':'https://foreign.test'}))
            self.assertEqual(error.exception.code,403);self.assertEqual(self.path.read_bytes(),before)
        finally:server.shutdown();server.server_close()
