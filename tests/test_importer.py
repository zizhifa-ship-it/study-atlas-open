"""一链接入库完整链路；不消耗真实模型额度。"""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from importer import AutoImporter, youtube_url
from integrations import IntegrationError
from server import LibraryStore

class FakeAI:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = 0
        self.prompts = []
        self.captions = True
        self.before_reply = lambda: None
    def read(self, name):
        return {}
    def transcript(self, url):
        if not self.captions:
            raise IntegrationError("测试：字幕不可用")
        return {"transcript":"课程介绍协议分层，说明 IP 地址用于寻址，ICMP 可以协助诊断网络故障。"}
    def harness_generate(self, prompt):
        self.calls += 1
        self.prompt = prompt
        self.prompts.append(prompt)
        self.before_reply()
        return {"model":"test", "content":json.dumps({"aiTitle":"网络协议入门", "categoryId":"network", "categoryName":"", "tags":["网络基础"], "summary":"IP 用于寻址；ICMP 协助诊断。[S1]"})}

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / "library.json"
        path.write_text(json.dumps({"schemaVersion":1,"revision":0,"categories":[{"id":"network","name":"网络工程","parentId":None,"color":"green","description":""}],"videos":[],"insights":[]}))
        self.store = LibraryStore(path)
        self.ai = FakeAI()
        self.importer = AutoImporter(self.store,self.ai)
        self.meta = patch('importer.metadata',return_value={"title":"协议入门测试","author":"测试频道"})
        self.meta.start()
    def tearDown(self):
        self.importer.queue.join()
        self.meta.stop()
        self.temp.cleanup()
    def submit(self):
        r = self.importer.submit("https://youtu.be/abcdefghijk?si=tracking")
        self.importer.queue.join()
        return self.store.read()["videos"][0], r
    def test_url_to_classification_notes_and_persistence(self):
        v, _ = self.submit()
        self.assertEqual(v["url"],"https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(v["categoryId"],"network")
        self.assertEqual(v["title"],"协议入门测试")
        self.assertEqual(v["aiTitle"],"网络协议入门")
        self.assertIn("[S1]",v["summary"])
        self.assertEqual(v["automation"]["status"],"ready")
        self.assertEqual(LibraryStore(self.store.path).read(),self.store.read())
        self.assertNotIn('cookies',self.ai.prompt)
        self.assertTrue(self.importer.submit(v["url"])["duplicate"])
        self.assertEqual(self.ai.calls,1)
    def test_missing_captions_never_creates_fake_notes(self):
        self.ai.captions = False
        v, _ = self.submit()
        self.assertEqual(v["categoryId"],"network")
        self.assertEqual(v["summary"],"")
        self.assertEqual(v["automation"]["status"],"needs_content")
        data=self.store.read()
        data["videos"][0]["transcript"]="用户补充的字幕，包含足够详细的网络协议和故障排除课程资料。"
        self.store.save(data)
        self.importer.submit(v["url"],retry=True)
        self.importer.queue.join()
        self.assertEqual(self.store.read()["videos"][0]["automation"]["status"],"ready")
    def test_user_edits_during_generation_are_preserved(self):
        def edit():
            data=self.store.read()
            data["videos"][0]["summary"]="我正在写的个人笔记"
            data["videos"][0]["favorite"]=True
            self.store.save(data)
        self.ai.before_reply=edit
        v,_=self.submit()
        self.assertEqual(v["summary"],"我正在写的个人笔记")
        self.assertTrue(v["favorite"])
        self.assertIn("AI 新整理",v["notes"][-1]["text"])
    def test_untrusted_urls_rejected_before_network(self):
        for url in ["http://localhost:3080/","https://youtube.com.evil.test/watch?v=abcdefghijk","https://user@youtube.com/watch?v=abcdefghijk"]:
            with self.assertRaises(IntegrationError):youtube_url(url)
    def test_network_error_preserves_link(self):
        with patch('importer.metadata',side_effect=IntegrationError("识别失败")):
            v,_=self.submit()
        self.assertEqual(v["automation"]["status"],"failed")
        self.assertEqual(v["summary"],"")
        self.assertEqual(self.ai.calls,0)

    def test_long_video_covers_tail_and_replaces_old_summary_with_history(self):
        self.ai.transcript = lambda url: {"transcript":"分层网络课程。" * 14000 + "尾部独有概念：负载均衡适用条件"}
        v,_ = self.submit()
        self.assertEqual(self.ai.calls,3)
        self.assertTrue(any("尾部独有概念" in prompt for prompt in self.ai.prompts))
        self.assertIn("全部字幕已分段",v["summary"])
        self.importer.submit(v["url"],retry=True)
        self.importer.queue.join()
        self.assertEqual(self.store.read()["videos"][0]["summary"],v["summary"])

    def test_detailed_import_invokes_knowledge_builder_exactly_once(self):
        with patch('importer.make_knowledge') as build:
            self.importer.submit("https://youtu.be/abcdefghijk",detailed=True)
            self.importer.queue.join()
        self.assertEqual(build.call_count,1)
