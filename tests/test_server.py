"""只使用临时副本测试，不改动你的学习资料。"""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from http_helpers import authorized_request as Request

from server import ConflictError, LibraryStore, ROOT, ValidationError, make_handler, validate_library, initialize_local_library
from http.server import ThreadingHTTPServer


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "library.json"
        fixture = {"schemaVersion": 1, "revision": 0,
                   "categories": [
                       {"id":"network", "name":"网络工程", "parentId":None, "color":"green", "description":""},
                       {"id":"network-basics", "name":"网络基础", "parentId":"network", "color":"green", "description":""}],
                   "videos": [{"id":"sample", "title":"测试课程", "url":"https://example.org/video",
                               "categoryId":"network-basics", "author":"测试作者", "durationSec":506,
                               "tags":[], "status":"todo", "favorite":False, "summary":"", "notes":[],
                               "createdAt":"2026-10-25", "updatedAt":"2026-10-25"}]}
        self.path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
        self.store = LibraryStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_category_video_note_survive_reopen_and_backup(self):
        data = self.store.read()
        data["categories"].append({"id":"test-category", "name":"测试分类", "parentId":"network", "color":"blue", "description":""})
        item = copy.deepcopy(data["videos"][0])
        item.update(id="test-video", url="https://example.com/course", categoryId="test-category", summary="测试总结")
        item["notes"] = [{"id":"test-note", "timeSec":265, "text":"ICMP 测试笔记", "createdAt":"2026-10-25"}]
        data["videos"].append(item)
        saved = self.store.save(data)
        restored = LibraryStore(self.path).read()
        self.assertEqual(saved, restored)
        self.assertEqual(restored["videos"][-1]["notes"][0]["timeSec"], 265)
        backups = list((self.path.parent / ".backups").glob("*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(len(json.loads(backups[0].read_text())["videos"]), 1)

    def test_invalid_import_does_not_overwrite_original(self):
        original = self.path.read_bytes()
        bad = self.store.read()
        bad["videos"][0]["url"] = "javascript:alert(1)"
        with self.assertRaises(ValidationError):
            self.store.save(bad)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.path.parent / ".backups").exists())

    def test_stale_tab_cannot_overwrite_a_new_save(self):
        first, stale = self.store.read(), self.store.read()
        first["videos"][0]["summary"] = "第一份已保存的笔记"
        self.store.save(first)
        stale["videos"][0]["summary"] = "过期页面的内容"
        with self.assertRaises(ConflictError):
            self.store.save(stale)
        self.assertEqual(self.store.read()["videos"][0]["summary"], "第一份已保存的笔记")

    def test_category_cycle_and_missing_category_are_rejected(self):
        bad = self.store.read()
        bad["categories"][0]["parentId"] = "network-basics"
        with self.assertRaises(ValidationError):
            validate_library(bad)
        bad = self.store.read()
        bad["videos"][0]["categoryId"] = "missing"
        with self.assertRaises(ValidationError):
            validate_library(bad)

    def test_duplicate_link_is_rejected(self):
        bad = self.store.read()
        duplicate = copy.deepcopy(bad["videos"][0])
        duplicate["id"] = "another-video"
        bad["videos"].append(duplicate)
        with self.assertRaises(ValidationError):
            self.store.save(bad)

    def test_first_run_creates_private_data_without_overwriting_personal_records(self):
        root = Path(self.temp.name) / "fresh-clone"
        (root / "data").mkdir(parents=True)
        template = {"schemaVersion":1,"revision":0,"categories":[],"videos":[],"insights":[]}
        (root / "data/library.example.json").write_text(json.dumps(template), encoding="utf-8")
        path = initialize_local_library(root)
        self.assertEqual(json.loads(path.read_text()), template)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        personal = b'{"saved-personal-data":"keep-this"}'
        path.write_bytes(personal)
        self.assertEqual(initialize_local_library(root).read_bytes(), personal)

    def test_http_save_reload_and_local_boundary(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = "http://127.0.0.1:" + str(server.server_port)
        try:
            with urlopen(base + "/api/library") as response:
                data = json.load(response)
            data["videos"][0]["summary"] = "通过真实 HTTP 写入的总结"
            req = Request(base + "/api/library", data=json.dumps(data).encode(), method="PUT", headers={"Content-Type":"application/json"})
            with urlopen(req) as response:
                self.assertEqual(response.status, 200)
            with urlopen(base + "/api/library") as response:
                self.assertEqual(json.load(response)["videos"][0]["summary"], "通过真实 HTTP 写入的总结")
            for path in ["/.git/config", "/data/library.json", "/server.py"]:
                with self.assertRaises(HTTPError) as raised:
                    urlopen(base + path)
                self.assertEqual(raised.exception.code, 404)
            malicious = Request(base + "/api/library", data=b"{}", method="PUT", headers={"Content-Type":"application/json", "Origin":"https://example.com"})
            with self.assertRaises(HTTPError) as raised:
                urlopen(malicious)
            self.assertEqual(raised.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
