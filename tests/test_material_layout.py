import copy
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from integrations import IntegrationError, Integrations
from transcript_sources import acquire_transcript, original_tracks, parse_transcript, asr_status
from note_layout import clean_cornell, clean_procedure, format_existing
from server import LibraryStore
from test_practice import fixture

TEXT = 'DHCP automatically assigns IP addresses to devices when they join a network.'
URL = 'https://www.youtube.com/watch?v=abcdefghijk'


def caption_metadata():
    return {'language': 'en', 'automatic_captions': {
        'zh-Hans': [{'url': 'https://www.youtube.com/api/timedtext?v=abcdefghijk&tlang=zh-Hans', 'ext': 'json3'}],
        'en-orig': [{'url': 'https://www.youtube.com/api/timedtext?v=abcdefghijk&lang=en', 'ext': 'json3'}]}}


class MaterialTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_original_only_and_cached_reuse_ignore_translation_failure(self):
        result=SimpleNamespace(stdout=json.dumps(caption_metadata()),returncode=0)
        raw=json.dumps({'events':[{'segs':[{'utf8':TEXT}]}]}).encode()
        with patch('transcript_sources.ytdlp_command',return_value=['yt-dlp']),patch('transcript_sources.subprocess.run',return_value=result) as run,patch('transcript_sources.urlopen',return_value=io.BytesIO(raw)) as fetch:
            first=acquire_transcript(self.root,URL);second=acquire_transcript(self.root,URL)
        self.assertEqual(first['transcript'],TEXT);self.assertEqual(first['language'],'en');self.assertTrue(second['cached'])
        self.assertNotIn('tlang',fetch.call_args.args[0].full_url);self.assertEqual(fetch.call_count,1);self.assertEqual(run.call_count,1)
        self.assertEqual((self.root/'.local/transcripts/abcdefghijk.json').stat().st_mode & 0o777,0o600)
    def test_original_429_switches_to_asr_without_retrying_translation(self):
        result=SimpleNamespace(stdout=json.dumps(caption_metadata()),returncode=0)
        fallback={'transcript':TEXT,'kind':'asr','source':'本机语音转录','language':'en'}
        with patch('transcript_sources.ytdlp_command',return_value=['yt-dlp']),patch('transcript_sources.subprocess.run',return_value=result),patch('transcript_sources.urlopen',side_effect=HTTPError(URL,429,'rate limited',{},None)) as fetch,patch('transcript_sources.run_asr',return_value=fallback) as asr:
            actual=acquire_transcript(self.root,URL)
        self.assertEqual(actual['kind'],'asr');self.assertEqual(fetch.call_count,1);self.assertEqual(asr.call_count,1)
    def test_non_english_original_is_supported_and_live_chat_is_ignored(self):
        metadata={'language':'ja','automatic_captions':{'ja-orig':[{'url':'https://www.youtube.com/api/timedtext?lang=ja','ext':'vtt'}],
                  'en':[{'url':'https://www.youtube.com/api/timedtext?lang=ja&tlang=en','ext':'vtt'}],
                  'live_chat':[{'url':'https://www.youtube.com/api/timedtext?lang=en','ext':'vtt'}]}}
        self.assertEqual([t['language'] for t in original_tracks(metadata)],['ja'])
    def test_no_source_never_creates_notes_from_a_title(self):
        result=SimpleNamespace(stdout='{}',returncode=0)
        with patch('transcript_sources.ytdlp_command',return_value=['yt-dlp']),patch('transcript_sources.subprocess.run',return_value=result):
            with self.assertRaises(IntegrationError):acquire_transcript(self.root,URL,allow_asr=False)
        self.assertFalse((self.root/'.local/transcripts/abcdefghijk.json').exists())
    def test_srt_and_vtt_keep_content_without_timing_headers(self):
        text='WEBVTT\n\n1\n00:00:00.000 --> 00:00:10.000\n'+TEXT+'\n'+TEXT+'\n'
        self.assertEqual(parse_transcript(text,'vtt'),TEXT)
        with self.assertRaises(IntegrationError):parse_transcript('只有标题','txt')
    def test_private_or_local_urls_are_rejected_before_any_network(self):
        with patch('transcript_sources.subprocess.run') as run:
            for url in ['http://127.0.0.1:3080','https://user@youtube.com/watch?v=abcdefghijk','https://youtube.com.evil.org/watch?v=abcdefghijk']:
                with self.assertRaises(IntegrationError):acquire_transcript(self.root,url)
            run.assert_not_called()


class LayoutAI:
    def __init__(self):self.lock=threading.Lock();self.before=lambda:None;self.bad=False
    def read(self,name):return {}
    def harness_generate(self,prompt):
        self.before();cornell={'cues':['DHCP 解决什么问题？','寻址与地址分配如何配合？'],'summary':'DHCP 自动分配 IP 地址，IP 用于跨网络寻址。[S1]'}
        return {'model':'mock','content':json.dumps({'cornell':cornell,'modules':[{'id':'bad' if self.bad else 'm1','cornell':cornell,'procedure':None}]},ensure_ascii=False)}


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'library.json';self.path.write_text(json.dumps(fixture(),ensure_ascii=False));self.store=LibraryStore(self.path);self.ai=LayoutAI()
    def tearDown(self):self.tmp.cleanup()
    def test_ai_format_keeps_body_questions_and_previous_personal_notes(self):
        before=self.store.read();result=format_existing(self.store,self.ai,'v1',lambda m:None)
        self.assertEqual(result['videos'][0]['summary'],before['videos'][0]['summary'])
        self.assertEqual(result['videos'][0]['knowledge']['modules'][0]['notes'],before['videos'][0]['knowledge']['modules'][0]['notes'])
        self.assertEqual(result['videos'][0]['knowledge']['modules'][0]['questions'],before['videos'][0]['knowledge']['modules'][0]['questions'])
        self.assertEqual(len(result['videos'][0]['cornell']['cues']),2)
        self.assertIn('summary',result['videos'][0]['knowledge']['modules'][0]['cornell'])
    def test_invalid_format_does_not_overwrite_existing_notes(self):
        self.ai.bad=True;original=self.path.read_bytes()
        with self.assertRaises(IntegrationError):format_existing(self.store,self.ai,'v1',lambda m:None)
        self.assertEqual(original,self.path.read_bytes());self.assertFalse(self.ai.lock.locked())
    def test_new_body_during_format_is_preserved(self):
        def edit():
            data=self.store.read();data['videos'][0]['knowledge']['modules'][0]['notes']+=' 新的课后解释。';self.store.save(data)
        self.ai.before=edit
        with self.assertRaises(IntegrationError):format_existing(self.store,self.ai,'v1',lambda m:None)
        self.assertIn('新的课后解释',self.store.read()['videos'][0]['knowledge']['modules'][0]['notes'])
    def test_procedure_needs_goal_action_expected_and_verification(self):
        with self.assertRaises(IntegrationError):clean_procedure({'goal':'测试网络','steps':[{'action':'ping'}],'conclusion':'资料未说明'})
        with self.assertRaises(IntegrationError):clean_cornell({'cues':[],'summary':'空白提示栏不能算完整康奈尔笔记'})
    def test_cornell_pdf_long_body_is_paginated_and_complete(self):
        try:
            from pdf_export import make_pdf,select_notes
            from pypdf import PdfReader
        except ImportError:self.skipTest('PDF runtime unavailable')
        data=self.store.read();data['videos'][0]['knowledge']['modules'][0]['notes']=('这是跨页长记录，需要保持完整且不能裁掉末尾。[S1]\n\n'*150)+'尾部验证标记：所有内容应保留。'
        pdf=make_pdf(select_notes(data));reader=PdfReader(io.BytesIO(pdf));all_text='\n'.join(p.extract_text() for p in reader.pages)
        self.assertIn('提示与问题',all_text);self.assertIn('归纳小结',all_text);self.assertIn('尾部验证标记',all_text)
        self.assertGreater(len(reader.pages),3)


if __name__=='__main__':unittest.main()

class FormatRepairTests(unittest.TestCase):
    def test_module_format_error_gets_one_bounded_repair(self):
        from knowledge import generate_module
        from test_knowledge import module
        good=module();bad=dict(good,pitfalls=['易错点']*9);calls=[]
        def model(prompt):
            calls.append(prompt);return {'content':json.dumps(bad if len(calls)==1 else good,ensure_ascii=False)}
        result=generate_module(model,'课程资料', {k:good[k] for k in ['id','title','objective','prerequisites']},lambda m:None)
        self.assertEqual(result['notes'],good['notes']);self.assertEqual(len(calls),2);self.assertIn('易错点格式不正确',calls[1])
    def test_network_error_does_not_automatically_retry(self):
        from knowledge import generate_module
        from unittest.mock import Mock
        model=Mock(side_effect=IntegrationError('连接失败'))
        with self.assertRaises(IntegrationError):generate_module(model,'资料',{},lambda m:None)
        self.assertEqual(model.call_count,1)
