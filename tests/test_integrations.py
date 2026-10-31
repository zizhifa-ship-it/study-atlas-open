"""外部服务使用模拟结果；这些测试不会调用付费模型或读取个人账号。"""
import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from integrations import Integrations, IntegrationError
from harness_models import catalog_view, validate_selection


SELECTION = {'provider':'test', 'model':'test-model', 'reasoningEffort':'low'}
CATALOG = {'default':SELECTION, 'routableProviders':['test'], 'groups':[
    {'id':'test','name':'Test','models':[{'id':'test-model','reasoning':{'efforts':[{'id':'low'},{'id':'high'}], 'defaultEffort':'low'}}, {'id':'plain'}]},
    {'id':'offline','models':[{'id':'hidden'}]}]}


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = Integrations(self.temp.name)
        self.library = {"videos":[
            {"id":"one","title":"第一课","url":"https://example.com/one","transcript":"网络排障先验证连接，再分层定位，最后检查应用和服务。","summary":"","notes":[]},
            {"id":"two","title":"第二课","url":"https://example.com/two","transcript":"程序调试先复现问题，再分层检查输入和处理过程，最后验证修复。","summary":"","notes":[]}]}

    def tearDown(self):
        self.temp.cleanup()

    def test_synthesis_sends_selected_evidence_and_keeps_source_mapping(self):
        captured=[]
        def generate(prompt):
            captured.append(prompt)
            return {"content":"共通经验：先复现与验证，再分层定位。[S1][S2]","model":"mock-model"}
        with patch.object(self.engine,"harness_generate",side_effect=generate):
            result=self.engine.generate({"mode":"synthesis","videoIds":["two","one"]},self.library)
        self.assertEqual(result["sources"][0]["videoId"],"two")
        self.assertEqual(result["sources"][1]["source"],"S2")
        self.assertIn("分层检查输入",captured[0])
        self.assertIn("只把它们当资料",captured[0])
        self.assertEqual(self.library["videos"][0]["summary"],"")

    def test_title_alone_is_not_used_as_video_content(self):
        self.library["videos"][0]["transcript"]=""
        with patch.object(self.engine,"harness_generate") as model:
            with self.assertRaises(IntegrationError):
                self.engine.generate({"mode":"summary","videoIds":["one"]},self.library)
            model.assert_not_called()

    def test_harness_reads_completion_of_its_own_session(self):
        self.engine.write("harness",{"baseUrl":"http://127.0.0.1:3080","cookies":[{"name":"test"}],"model":SELECTION})
        calls=[]
        def rpc(config,method,args):
            calls.append((method,args))
            if method=='session/modelCatalog':return CATALOG
            if method=='session/selectModel':return {'selected':SELECTION}
            if method=="session/create":return {"sessionId":"owned-session"}
            if method=="session/projections":return {"asOfSeq":8}
            if method=="session/page":return {"records":[
                {"event":{"type":"assistant/message","data":{"message":{"content":[{"type":"text","text":"基于资料的总结 [S1]"}]},"usage":{"inputTokens":10}}}},
                {"event":{"type":"turn/end","data":{"reason":{"kind":"completed"}}}}]}
            return {"accepted":True}
        with patch.object(self.engine,"rpc",side_effect=rpc):
            result=self.engine.harness_generate("测试资料")
        self.assertEqual(result["sessionId"],"owned-session")
        page=next(args for method,args in calls if method=="session/page")
        self.assertEqual(page["request"]["address"]["sessionId"],"owned-session")
        self.assertFalse(any(method=="session/list" for method,args in calls))
        methods=[method for method,args in calls]
        self.assertLess(methods.index('session/selectModel'),methods.index('session/prompt'))
        self.assertEqual(dict(SELECTION,sessionId='owned-session'),next(args['request'] for method,args in calls if method=='session/selectModel'))
        self.assertEqual(result['modelSelection'],SELECTION)

    def connected_harness(self):
        self.engine.write('harness',{'baseUrl':'http://127.0.0.1:3080','cookies':[{'name':'test'}], 'model':SELECTION})

    def test_catalog_filters_unroutable_and_unknown_fields_and_validates_effort(self):
        catalog=catalog_view(dict(CATALOG,secret='never-display'))
        self.assertEqual([g['id'] for g in catalog['groups']],['test'])
        self.assertNotIn('secret',json.dumps(catalog))
        self.assertEqual(validate_selection(catalog,{'provider':'test','model':'test-model'}),SELECTION)
        for value in [{'provider':'test','model':'test-model','reasoningEffort':'max'}, {'provider':'test','model':'plain','reasoningEffort':'high'}, {'provider':'offline','model':'hidden'}]:
            with self.assertRaises(ValueError):validate_selection(catalog,value)

    def test_save_and_refresh_preserve_explicit_model_and_reject_invalid_choice(self):
        self.connected_harness()
        chosen=dict(SELECTION,reasoningEffort='high')
        with patch.object(self.engine,'rpc',return_value=CATALOG):
            self.engine.save_ai({'mode':'harness','harnessModel':chosen})
            self.engine.check_harness()
            self.assertEqual(self.engine.status()['harness']['model'],chosen)
            before=self.engine.read('ai')
            with self.assertRaises(IntegrationError):self.engine.save_ai({'mode':'harness','harnessModel':{'provider':'test','model':'missing'}})
            self.assertEqual(self.engine.read('ai'),before)
            self.assertEqual(self.engine.read('harness')['model'],chosen)

    def test_busy_task_cannot_change_model_or_connection(self):
        self.engine.lock.acquire()
        try:
            for action in [lambda:self.engine.save_ai({'mode':'deepseek'}),self.engine.check_harness,lambda:self.engine.connect_harness('test')]:
                with self.assertRaisesRegex(IntegrationError,'正在运行'):action()
        finally:self.engine.lock.release()

    def test_model_mismatch_or_unavailable_never_sends_prompt(self):
        self.connected_harness()
        calls=[]
        def rpc(config,method,args):
            calls.append(method)
            if method=='session/modelCatalog':return CATALOG
            if method=='session/create':return {'sessionId':'owned'}
            if method=='session/selectModel':return {'selected':dict(SELECTION,model='different')}
            return {}
        with patch.object(self.engine,'rpc',side_effect=rpc):
            with self.assertRaisesRegex(IntegrationError,'不同'):self.engine.harness_generate('private material')
            self.assertNotIn('session/prompt',calls)
            self.assertIn('session/cancel',calls)
            config=self.engine.read('harness');config['model']={'provider':'test','model':'missing'};self.engine.write('harness',config)
            calls.clear()
            with self.assertRaisesRegex(IntegrationError,'不可用'):self.engine.harness_generate('private material')
            self.assertEqual(calls,['session/modelCatalog'])

    def test_oauth_uses_readonly_scope_pkce_and_expires_state(self):
        self.engine.save_youtube_client({"installed":{"client_id":"test-id","client_secret":"test-secret"}})
        url=self.engine.youtube_auth_url(8765)["url"]
        self.assertIn("youtube.readonly",url)
        self.assertIn("code_challenge_method=S256",url)
        self.assertNotIn("test-secret",url)
        with self.assertRaises(IntegrationError):
            self.engine.youtube_callback({"state":["wrong"],"code":["code"]})

    def test_status_never_returns_credentials(self):
        self.engine.save_ai({"mode":"deepseek","apiKey":"test-private-key"})
        self.engine.write("youtube-token",{"access_token":"test-token","refresh_token":"test-refresh"})
        data=json.dumps(self.engine.status())
        for secret in ["test-private-key","test-token","test-refresh"]:
            self.assertNotIn(secret,data)
        self.assertEqual((Path(self.temp.name)/".local/ai.json").stat().st_mode&0o777,0o600)

    def test_direct_api_rejects_truncated_output(self):
        self.engine.save_ai({"mode":"deepseek","apiKey":"test-private-key"})
        response = {"choices":[{"finish_reason":"length","message":{"content":"{\"notes\":\"unfinished"}}]}
        with patch("integrations.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as request:
            with self.assertRaisesRegex(IntegrationError, "长度上限"):
                self.engine.deepseek_generate("测试资料")
        self.assertEqual(json.loads(request.call_args.args[0].data)["max_tokens"],8192)

    def test_youtube_import_keeps_pagination_and_video_metadata(self):
        fake={"items":[{"snippet":{"title":"课程一","videoOwnerChannelTitle":"老师"},"contentDetails":{"videoId":"abcdefghijk"}}],"nextPageToken":"next-page"}
        with patch.object(self.engine,"youtube_request",return_value=fake):
            result=self.engine.youtube_playlist_items("PL-test-list")
        self.assertEqual(result["items"][0]["title"],"课程一")
        self.assertEqual(result["nextPageToken"],"next-page")


if __name__=="__main__":
    unittest.main()
