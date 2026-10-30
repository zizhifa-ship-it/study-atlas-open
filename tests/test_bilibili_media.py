import copy
import io
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from http_helpers import authorized_request as Request
from integrations import IntegrationError,Integrations
from video_sources import canonical_video_url
from bilibili_sources import canonical_bilibili,video_info,acquire_bilibili,ShareRedirects,subtitle_url
from video_media import validate_thumbnail,validate_visuals,frame_plan,build_visuals
from server import LibraryStore,make_handler
from test_practice import fixture

URL='https://www.bilibili.com/video/BV1234567890/'
TEXT='IP アドレスはネットワーク上の機器を識別するための論理アドレスです。'
INFO={'code':0,'data':{'title':'网络课程','bvid':'BV1234567890','owner':{'name':'测试讲师'},'pic':'https://i0.hdslb.com/test.jpg','pages':[{'cid':101,'part':'前言','duration':10},{'cid':202,'part':'寻址','duration':200}]}}

class BilibiliTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def test_share_text_canonicalization_tracks_and_parts(self):
  self.assertEqual(canonical_video_url('【网络课程】 '+URL+'?p=2&spm_id_from=abc'),URL+'?p=2')
  self.assertEqual(canonical_bilibili(URL+'?p=01'),URL)
  self.assertEqual(canonical_bilibili('https://m.bilibili.com/video/av123/?p=2'),'https://www.bilibili.com/video/av123/?p=2')
  for bad in ['http://127.0.0.1/','https://user@www.bilibili.com/video/BV1234567890','https://www.bilibili.com.evil.org/video/BV1234567890',URL+'?p=0',URL+'?p=501']:
   with self.assertRaises(IntegrationError):canonical_video_url(bad)
 def test_short_link_resolution_uses_only_video_domains(self):
  response=type('Result',(),{'geturl':lambda self:URL+'?p=2','__enter__':lambda self:self,'__exit__':lambda *args:None})()
  with patch('bilibili_sources.build_opener') as build:
   build.return_value.open.return_value=response
   self.assertEqual(canonical_bilibili('https://b23.tv/AbCd12'),URL+'?p=2')
  for destination in ['https://evil.org/x','http://127.0.0.1/','https://user@www.bilibili.com/x']:
   with self.assertRaises(IntegrationError):ShareRedirects().redirect_request(Request('https://b23.tv/AbCd12'),None,302,'',{},destination)
 def test_part_metadata_does_not_mix_other_episodes(self):
  with patch('bilibili_sources.get_json',return_value=INFO):actual=video_info(URL+'?p=2')
  self.assertEqual(actual['cid'],202);self.assertIn('P2 寻址',actual['title']);self.assertEqual(actual['durationSec'],200)
  with patch('bilibili_sources.get_json',return_value=INFO):
   with self.assertRaises(IntegrationError):video_info(URL+'?p=3')
 def test_subtitle_json_works_in_non_chinese_language_and_private_cache(self):
  info={'bvid':'BV1234567890','cid':202}
  player={'data':{'subtitle':{'subtitles':[{'lan':'ja','subtitle_url':'//aisubtitle.hdslb.com/test.json'},{'lan':'danmaku','subtitle_url':'https://comment.bilibili.com/test.xml'}]}}}
  body={'body':[{'from':1,'to':5,'content':TEXT}]}
  with patch('bilibili_sources.video_info',return_value=info),patch('bilibili_sources.get_json',side_effect=[player,body]) as get,patch('transcript_sources.run_asr') as asr:
   first=acquire_bilibili(self.root,URL+'?p=2');second=acquire_bilibili(self.root,URL+'?p=2')
  self.assertEqual(first['transcript'],TEXT);self.assertEqual(first['language'],'ja');self.assertTrue(second['cached']);self.assertEqual(get.call_count,2);asr.assert_not_called()
  self.assertEqual((self.root/'.local/transcripts/bili-BV1234567890-p2.json').stat().st_mode&0o777,0o600)
 def test_no_captions_uses_original_audio_not_danmaku(self):
  with patch('bilibili_sources.video_info',return_value={'bvid':'BV1234567890','cid':101}),patch('bilibili_sources.get_json',return_value={'data':{'subtitle':{'subtitles':[{'lan':'danmaku','subtitle_url':'https://comment.bilibili.com/1.xml'}]}}}),patch('transcript_sources.run_asr',return_value={'transcript':TEXT,'language':'ja','kind':'asr'}) as asr:
   actual=acquire_bilibili(self.root,URL)
  self.assertEqual(actual['kind'],'asr');asr.assert_called_once();self.assertIn('本机语音转录',actual['source'])
 def test_no_material_does_not_invent_notes(self):
  with patch('bilibili_sources.video_info',return_value={'bvid':'BV1234567890','cid':101}),patch('bilibili_sources.get_json',return_value={}):
   with self.assertRaises(IntegrationError):acquire_bilibili(self.root,URL,allow_asr=False)
  self.assertFalse(list((self.root/'.local/transcripts').glob('*.json')))
 def test_caption_url_cannot_fetch_private_or_unrelated_hosts(self):
  for bad in ['http://127.0.0.1/x','https://evil.org/x','https://user@i0.hdslb.com/x']:
   with self.assertRaises(IntegrationError):subtitle_url(bad)

class MediaTests(unittest.TestCase):
 def test_asset_and_thumbnail_validation_rejects_paths_and_private_urls(self):
  for bad in ['http://127.0.0.1/x','https://evil.org/a.jpg','data:image/png;base64,abc']:
   with self.assertRaises(IntegrationError):validate_thumbnail(bad)
  with self.assertRaises(IntegrationError):validate_visuals({'status':'ready','cover':'../../secret','frames':[]})
 def test_frame_times_match_evidence_when_timestamps_are_available(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);folder=root/'.local/transcripts';folder.mkdir(parents=True)
   (folder/'abcdefghijk.json').write_text(json.dumps({'segments':[{'start':i*20,'text':'evidence-number-%d-is-here'%i} for i in range(3)]}))
   video={'url':'https://www.youtube.com/watch?v=abcdefghijk','knowledge':{'modules':[{'id':'m'+str(i),'title':'模块'+str(i),'evidence':['evidence-number-%d-is-here'%i]} for i in range(3)]}}
   actual=frame_plan(root,video,100)
   self.assertEqual([x['moduleId'] for x in actual],['m0','m1','m2']);self.assertEqual(actual[-1]['timeSec'],40)
 def test_cover_only_failure_does_not_remove_text_or_personal_notes(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);data=fixture();data['videos'][0]['url']='https://www.youtube.com/watch?v=abcdefghijk';path=root/'library.json';path.write_text(json.dumps(data));store=LibraryStore(path);before=store.read()['videos'][0];ai=Integrations(root)
   with patch('video_media.cache_cover',return_value='a'*64+'.jpg'):
    result=build_visuals(store,ai,'v1',lambda m:None)
   saved=result['videos'][0];self.assertEqual(saved['summary'],before['summary']);self.assertEqual(saved['knowledge'],before['knowledge']);self.assertEqual(saved['visuals']['status'],'partial')
 def test_later_module_uses_later_quote_and_gallery_stays_chronological(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);folder=root/'.local/transcripts';folder.mkdir(parents=True)
   quotes=['opening-quote-original','middle-quote-original','ending-quote-original']
   (folder/'abcdefghijk.json').write_text(json.dumps({'segments':[{'start':t,'text':q} for t,q in zip([10,100,180],quotes)]}))
   video={'url':'https://www.youtube.com/watch?v=abcdefghijk','knowledge':{'modules':[{'id':'m'+str(i),'title':'模块'+str(i),'evidence':[quotes[0],quotes[i]]} for i in range(3)]}}
   actual=frame_plan(root,video,200)
   self.assertEqual([x['timeSec'] for x in actual],[10,100,180])
   self.assertEqual(actual[-1]['moduleId'],'m2')
 def test_local_media_route_blocks_path_traversal_and_foreign_page(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);path=root/'library.json';path.write_text(json.dumps(fixture()));store=LibraryStore(path);ai=Integrations(root)
   folder=root/'.local/media';folder.mkdir(parents=True);name='a'*64+'.jpg';(folder/name).write_bytes(b'\xff\xd8test')
   server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store,ai));threading.Thread(target=server.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(server.server_port)
   try:
    response=urlopen(base+'/api/media/'+name);self.assertEqual(response.headers['Content-Type'],'image/jpeg');self.assertEqual(response.read(),b'\xff\xd8test')
    for url,headers in [(base+'/api/media/../library.json',{}),(base+'/api/media/'+name,{'Sec-Fetch-Site':'cross-site'})]:
     with self.assertRaises(HTTPError):urlopen(Request(url,headers=headers))
   finally:server.shutdown();server.server_close()

class IllustratedExportTests(unittest.TestCase):
 def test_pdf_embeds_local_cover_and_frame_with_cornell_content(self):
  try:
   from PIL import Image
   from pypdf import PdfReader
   from pdf_export import make_pdf,select_notes
  except ImportError:self.skipTest('PDF dependencies unavailable')
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);name='a'*64+'.png';Image.new('RGB',(320,180),(50,100,75)).save(folder/name)
   data=fixture();data['videos'][0]['visuals']={'status':'ready','cover':name,'frames':[{'asset':name,'timeSec':80,'label':'地址分配画面','moduleId':'m1'}],'message':'测试图片','createdAt':'2026-10-30'}
   payload=select_notes(data);payload['mediaRoot']=str(folder);reader=PdfReader(io.BytesIO(make_pdf(payload)))
   text='\n'.join(p.extract_text() for p in reader.pages)
   for value in ['图文导学','原视频封面','1:20','提示与问题','归纳小结']:self.assertIn(value,text)
   self.assertGreater(sum(len(p.images) for p in reader.pages),0)
