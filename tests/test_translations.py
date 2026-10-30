import copy
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from http_helpers import authorized_request as Request
from urllib.error import HTTPError
from pathlib import Path
from integrations import IntegrationError
from server import LibraryStore, make_handler
from test_practice import fixture
from note_translations import note_fingerprint, translate_notes, localized_video
from pdf_export import select_notes


class TranslationAI:
    def __init__(self):self.lock=threading.Lock();self.cache={};self.calls=[];self.before=lambda:None;self.fail_at=None;self.drop=False
    def read(self,name):return copy.deepcopy(self.cache.get(name,{}))
    def write(self,name,value):self.cache[name]=copy.deepcopy(value)
    def harness_generate(self,prompt):
        self.calls.append(prompt);self.before()
        if len(self.calls)==self.fail_at:raise IntegrationError('模拟中途断线')
        value=json.loads(prompt.split('\n',1)[1])
        if 'notes' in value:
            value['title']='Address allocation';value['notes']='DHCP assigns IP addresses. [S1]'
            value['cornell']={'cues':['What does DHCP do?'],'summary':'DHCP assigns an IP address. [S1]'}
            if self.drop:value['questions']=[]
        else:
            value.update(title='Network course',summary='DHCP allocates addresses. [S1]',overview='Addressing and allocation.',cornell={'cues':['How are addresses assigned?'],'summary':'DHCP assigns IP addresses. [S1]'})
        return {'content':json.dumps(value),'model':'mock'}


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'library.json';self.path.write_text(json.dumps(fixture(),ensure_ascii=False));self.store=LibraryStore(self.path);self.ai=TranslationAI()
    def tearDown(self):self.tmp.cleanup()
    def run_translation(self):return translate_notes(self.store,self.ai,'v1','en',lambda m:None)
    def test_all_modules_save_without_changing_original_notes_or_quotes(self):
        before=self.store.read()['videos'][0];translated=self.run_translation();after=self.store.read()['videos'][0]
        for key in ['title','summary','knowledge','notes','transcript']:self.assertEqual(before[key],after[key])
        self.assertEqual(translated['modules'][0]['evidence'],before['knowledge']['modules'][0]['evidence'])
        self.assertEqual(translated['modules'][0]['id'],'m1');self.assertFalse(after['translations']['en']['stale'])
        self.assertEqual(localized_video(after,'en')['summary'],'DHCP allocates addresses. [S1]')
        self.assertIn('代码、公式',self.ai.calls[0])
    def test_saved_translation_uses_no_second_ai_call(self):
        self.run_translation();count=len(self.ai.calls);self.run_translation();self.assertEqual(count,len(self.ai.calls))
    def test_modified_original_invalidates_translation_and_export(self):
        self.run_translation();data=self.store.read();data['videos'][0]['summary']+=' 新的内容';self.store.save(data)
        saved=self.store.read();self.assertTrue(saved['videos'][0]['translations']['en']['stale'])
        with self.assertRaises(IntegrationError):select_notes(saved,'v1','en')
    def test_personal_annotations_do_not_invalidate_notes_translation(self):
        self.run_translation();data=self.store.read();old=note_fingerprint(data['videos'][0]);data['videos'][0]['notes'].append({'id':'my-note','timeSec':None,'text':'我自己的补充','createdAt':'2026-10-29'});saved=self.store.save(data)
        self.assertEqual(old,note_fingerprint(saved['videos'][0]));self.assertFalse(saved['videos'][0]['translations']['en']['stale'])
    def test_interrupted_job_resumes_from_completed_header(self):
        self.ai.fail_at=2
        with self.assertRaises(IntegrationError):self.run_translation()
        self.assertFalse(self.ai.lock.locked());self.assertNotIn('translations',self.store.read()['videos'][0])
        self.ai.fail_at=None;self.run_translation();self.assertEqual(len(self.ai.calls),3)
    def test_omitted_questions_are_rejected_and_original_is_preserved(self):
        self.ai.drop=True;before=self.path.read_bytes()
        with self.assertRaises(IntegrationError):self.run_translation()
        self.assertEqual(before,self.path.read_bytes())
    def test_edit_during_generation_is_not_overwritten(self):
        def edit():
            data=self.store.read();data['videos'][0]['summary']+=' 刚写的新内容';self.store.save(data)
        self.ai.before=edit
        with self.assertRaises(IntegrationError):self.run_translation()
        saved=self.store.read()['videos'][0];self.assertIn('刚写的新内容',saved['summary']);self.assertNotIn('translations',saved)
    def test_http_translation_queue_save_cache_and_external_origin(self):
        import time
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.store,self.ai))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base='http://127.0.0.1:'+str(server.server_port)
        def post(language='en',origin=None):
            return urlopen(Request(base+'/api/notes/translate',data=json.dumps({'videoId':'v1','language':language}).encode(),headers={'Content-Type':'application/json','Origin':origin or base}),timeout=10)
        try:
            self.assertFalse(json.load(post())['cached'])
            deadline=time.monotonic()+5
            while time.monotonic()<deadline and 'en' not in self.store.read()['videos'][0].get('translations',{}):time.sleep(.02)
            self.assertIn('en',self.store.read()['videos'][0]['translations'])
            count=len(self.ai.calls);self.assertTrue(json.load(post())['cached']);self.assertEqual(count,len(self.ai.calls))
            with self.assertRaises(HTTPError) as blocked:post(origin='https://other.example')
            self.assertEqual(blocked.exception.code,403)
            with self.assertRaises(HTTPError):post(language='xx')
        finally:server.shutdown();server.server_close()

    def test_selected_language_export_excludes_other_language_and_raw_material(self):
        self.run_translation();selected=select_notes(self.store.read(),'v1','en')['videos'][0]
        self.assertEqual(selected['summary'],'DHCP allocates addresses. [S1]');self.assertNotIn('transcript',selected);self.assertNotIn('translations',selected)
        with self.assertRaises(IntegrationError):select_notes(self.store.read(),'v1','xx')

if __name__=='__main__':unittest.main()
