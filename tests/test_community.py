"""新用户的独立模型、文字课程与只读自检。所有 AI 请求为模拟或本机临时服务。"""
import copy
import io
import json
import tempfile
import threading
import unittest
import os
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from compatible_ai import endpoint, save_profile, public_status, generate, models
from integrations import Integrations, IntegrationError, select_generator, selected_model
from ai_efficiency import model_identity
from materials import parse_material, is_material_url
from importer import AutoImporter
from server import LibraryStore, validate_library
from diagnostics import readiness
from test_practice import fixture
from test_knowledge import FakeKnowledgeAI


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.ai=Integrations(self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_endpoint_blocks_lan_userinfo_queries_and_untrusted_cloud(self):
        for value in ['http://192.168.1.1:8080/v1','http://example.com:11434/v1','http://user:secret@localhost:1234/v1','http://127.0.0.1:1234/v1?token=x','https://localhost:1234/v1','file:///tmp/x']:
            with self.assertRaises(ValueError):endpoint('ollama',value)
        with self.assertRaises(ValueError):endpoint('openrouter','https://foreign.test/api/v1')
        with self.assertRaises(ValueError):endpoint([], 'x')
        with self.assertRaises(ValueError):endpoint('ollama', [])
        self.assertEqual(endpoint('ollama','http://localhost:11434/v1/'),'http://127.0.0.1:11434/v1')
    def test_provider_credentials_are_isolated_and_not_exposed(self):
        ai={'apiKey':'deepseek-private'}
        save_profile(ai,{'provider':'openrouter','model':'model-a','apiKey':'router-private'})
        save_profile(ai,{'provider':'siliconflow','model':'model-b'})
        self.assertNotIn('apiKey',ai['compatibleProfiles']['siliconflow'])
        save_profile(ai,{'provider':'ollama','model':'local','apiKey':'local-secret'})
        save_profile(ai,{'provider':'ollama','baseUrl':'http://127.0.0.1:12345/v1','model':'local'})
        self.assertNotIn('apiKey',ai['compatibleProfiles']['ollama'])
        self.assertNotIn('private',json.dumps(public_status(ai)));self.assertNotIn('local-secret',json.dumps(public_status(ai)))
    def test_switching_compatible_provider_and_endpoint_isolates_cache_identity(self):
        self.ai.save_ai({'mode':'compatible','compatible':{'provider':'ollama','model':'same'}})
        first=model_identity(self.ai)
        self.ai.save_ai({'mode':'compatible','compatible':{'provider':'lmstudio','model':'same'}})
        self.assertNotEqual(first,model_identity(self.ai));self.assertEqual(selected_model(self.ai),'same')
        self.assertEqual(select_generator(self.ai),self.ai.compatible_generate)
    def test_local_models_and_generation_work_without_harness_or_api_key(self):
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path,self.headers.get('Authorization')))
                self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[{"id":"local-model"}]}')
            def do_POST(self):
                seen.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'整理完成'}}],'model':'local-model','usage':{'prompt_tokens':10,'completion_tokens':3}}).encode())
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            self.ai.save_ai({'mode':'compatible','compatible':{'provider':'ollama','baseUrl':'http://127.0.0.1:%d/v1'%server.server_port,'model':'local-model'}})
            self.assertEqual(self.ai.compatible_models()['models'][0]['id'],'local-model')
            result=self.ai.compatible_generate('依据这段课堂资料写笔记。')
            self.assertEqual(result['content'],'整理完成');self.assertEqual(seen[0],('/v1/models',None))
            self.assertEqual(seen[1]['model'],'local-model');self.assertFalse(seen[1]['stream']);self.assertNotIn('tools',seen[1])
            self.assertTrue(readiness(self.root,self.ai)['aiConfigured'])
        finally:server.shutdown();server.server_close()
    def test_model_lookup_can_use_unsaved_profile_without_persisting_credentials(self):
        before=self.ai.read('ai')
        with patch('compatible_ai.request_json',return_value=('openrouter',{'data':[{'id':'model-x','name':'模型 X'}]})) as request:
            result=self.ai.compatible_models({'provider':'openrouter','model':'','apiKey':'temporary-secret'})
        self.assertEqual(result['models'][0]['id'],'model-x');self.assertEqual(self.ai.read('ai'),before)
        self.assertEqual(request.call_args.args[0]['compatibleProfiles']['openrouter']['apiKey'],'temporary-secret')
    def test_truncated_or_invalid_model_output_is_rejected_without_retry(self):
        ai={};save_profile(ai,{'provider':'ollama','model':'local'})
        for reply in [{'choices':[{'finish_reason':'length','message':{'content':'unfinished'}}]}, {'choices':[{}]}, {'choices':[{'finish_reason':'stop','message':{'content':None}}]}]:
            with patch('compatible_ai.request_json',return_value=('ollama',reply)) as request:
                with self.assertRaises(ValueError):generate(ai,'source')
                self.assertEqual(request.call_count,1)
    def test_plain_markdown_preserves_code_and_rejects_unsupported_documents(self):
        content='# C 语言\n\n```c\n#include <stdio.h>\n  printf("hello");\n```\n'
        title,name,text=parse_material({'title':'C 课堂','filename':'C:\\private\\lesson.md','content':content})
        self.assertEqual(text,content);self.assertEqual(name,'lesson.md')
        with self.assertRaises(IntegrationError):parse_material({'title':'课','filename':'x.pdf','content':'a'*30})
        self.assertFalse(is_material_url('studyatlas://material/../../secret'))
    def test_material_save_without_ai_and_backup_roundtrip_preserves_personal_data(self):
        path=self.root/'library.json';path.write_text(json.dumps(fixture()));store=LibraryStore(path);engine=FakeKnowledgeAI();importer=AutoImporter(store,engine)
        before=store.read()['videos'][0]
        result=importer.submit_material({'title':'课堂说明','filename':'lesson.md','content':'# 课堂资料\n'+ '讲解寻址与 DHCP 的作用。'*4,'generate':False})
        course=result['library']['videos'][-1]
        self.assertTrue(is_material_url(course['url']));self.assertEqual(engine.calls,[]);self.assertEqual(course['transcriptInfo']['kind'],'imported')
        restored=validate_library(json.loads(json.dumps(result['library'])));self.assertEqual(restored['videos'][0],before)
        self.assertEqual(restored['videos'][-1]['transcript'],course['transcript'])
    def test_material_can_generate_knowledge_directly_without_video_fetch(self):
        path=self.root/'library.json';path.write_text(json.dumps(fixture()));store=LibraryStore(path);engine=FakeKnowledgeAI();importer=AutoImporter(store,engine)
        with patch('importer.metadata',side_effect=AssertionError('文字课不能读取视频')):
            result=importer.submit_material({'title':'网络课堂','content':'网络使用 IP 进行跨网寻址，DHCP 自动分配 IP 地址。TCP 会确认与重传，UDP 不提供可靠性保证。','generate':True})
            importer.queue.join()
        course=next(v for v in store.read()['videos'] if v['id']==result['videoId'])
        self.assertEqual(len(course['knowledge']['modules']),2);self.assertEqual(course['automation']['status'],'ready')
    def test_readiness_is_read_only_and_does_not_expose_paths_or_credentials(self):
        before=list(self.ai.local.glob('*.json'));result=readiness(self.root,self.ai)
        self.assertTrue(result['checks'][0]['ready']);self.assertFalse(result['aiConfigured'])
        self.assertNotIn(str(self.root),json.dumps(result));self.assertNotIn('apiKey',json.dumps(result))
        self.assertEqual(list(self.ai.local.glob('*.json')),before)
    def test_private_config_write_handles_platform_without_fchmod(self):
        with patch('os.fchmod',None,create=True):
            self.ai.write('settings-test',{'configured':True})
        self.assertEqual(self.ai.read('settings-test'),{'configured':True})
    def test_ytdlp_is_found_in_project_venv_without_shell_activation(self):
        from transcript_sources import ytdlp_prefix
        folder=self.root/'.venv'/('Scripts' if os.name=='nt' else 'bin');folder.mkdir(parents=True)
        program=folder/('yt-dlp.exe' if os.name=='nt' else 'yt-dlp');program.write_text('test-only')
        with patch('shutil.which',return_value=None),patch('sys.executable',str(self.root/'other-python')):
            self.assertEqual(ytdlp_prefix(self.root),[str(program)])
    @unittest.skipIf(os.name=='nt','POSIX launcher; Windows startup is covered by the Windows CI smoke test')
    def test_launcher_handles_spaces_and_forwards_arguments(self):
        folder=self.root/'Project With Spaces';folder.mkdir();env=folder/'.venv/bin';env.mkdir(parents=True)
        (env/'python').symlink_to(sys.executable)
        shutil.copy2(Path(__file__).resolve().parent.parent/'start.sh',folder/'start.sh')
        (folder/'server.py').write_text('import json,sys;print(json.dumps(sys.argv[1:]))')
        result=subprocess.run(['sh',str(folder/'start.sh'),'--port','9876'],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout),['--open','--port','9876'])
