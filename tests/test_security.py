"""本机恶意网页、伪造请求、限流、重定向和私有文件边界的回归验证。"""
import copy
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request
from integrations import Integrations
from security import NoRedirect, PublicRedirects, public_url, RateLimiter
from server import LibraryStore, make_handler, ValidationError
from test_practice import fixture


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        path = self.root/'library.json'; path.write_text(json.dumps(fixture()))
        self.store = LibraryStore(path); self.ai = Integrations(self.root)
        self.server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(self.store,self.ai))
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.port = self.server.server_port; self.origin = 'http://127.0.0.1:' + str(self.port)
        self.token = json.loads(self.request('GET','/api/security')[1])['token']
    def tearDown(self): self.server.shutdown(); self.server.server_close(); self.tmp.cleanup()
    def request(self, method, path, body=None, headers=None, authorized=False):
        headers = dict(headers or {})
        if authorized: headers['X-Study-Atlas-Token'] = self.token
        if body is not None: headers.setdefault('Content-Type','application/json')
        conn = http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        conn.request(method,path,body=body,headers=headers); response=conn.getresponse()
        result=response.status,response.read(),dict(response.getheaders());conn.close();return result
    def test_token_required_and_legitimate_page_can_save(self):
        data=json.dumps(self.store.read());before=self.store.path.read_bytes()
        self.assertEqual(self.request('PUT','/api/library',data)[0],403)
        self.assertEqual(self.store.path.read_bytes(),before)
        self.assertEqual(self.request('PUT','/api/library',data,{'Origin':self.origin,'Sec-Fetch-Site':'same-origin'},True)[0],200)
    def test_cross_site_and_other_local_port_cannot_read_private_api(self):
        for headers in [{'Sec-Fetch-Site':'cross-site'},{'Sec-Fetch-Site':'same-site'}, {'Origin':'null'}, {'Origin':'http://127.0.0.1:1234'}, {'Host':'evil.example:'+str(self.port)}]:
            for path in ['/api/library','/api/security','/api/integrations/status','/api/export']:
                self.assertEqual(self.request('GET',path,headers=headers)[0],403)
    def test_foreign_origin_rejected_even_with_token(self):
        status=self.request('PUT','/api/library',json.dumps(self.store.read()),{'Origin':'https://evil.example'},True)[0]
        self.assertEqual(status,403)
    def test_duplicate_host_and_token_headers_rejected(self):
        for header in ['Host','X-Study-Atlas-Token']:
            conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
            conn.putrequest('PUT','/api/library',skip_host=True)
            conn.putheader('Host','127.0.0.1:'+str(self.port));conn.putheader('X-Study-Atlas-Token',self.token)
            conn.putheader(header,'127.0.0.1:'+str(self.port) if header=='Host' else self.token)
            conn.putheader('Content-Type','application/json');conn.putheader('Content-Length','2');conn.endheaders(b'{}')
            response=conn.getresponse();self.assertEqual(response.status,403);response.read();conn.close()
    def test_ambiguous_and_nonfinite_json_rejected_without_saving(self):
        before=self.store.path.read_bytes()
        for body in ['{"revision":0,"revision":1}', '{"revision":NaN}', '['*1100+'0'+']'*1100]:
            self.assertEqual(self.request('PUT','/api/library',body,authorized=True)[0],400)
        self.assertEqual(self.store.path.read_bytes(),before)
    def test_chunked_or_oversized_body_rejected_before_read(self):
        for headers in [{'Transfer-Encoding':'chunked'}, {'Content-Length':str(4*1024*1024+1)}]:
            self.assertEqual(self.request('POST','/api/import','{}',headers,True)[0],400)
    def test_security_headers_and_no_permissive_cors(self):
        status,body,headers=self.request('GET','/')
        self.assertEqual(status,200);self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Frame-Options'],'DENY');self.assertEqual(headers['Referrer-Policy'],'no-referrer')
        self.assertNotIn('Access-Control-Allow-Origin',headers);self.assertNotIn('Python',headers['Server'])
    def test_api_rate_limit_prevents_unbounded_work(self):
        with patch.object(self.ai,'check_harness',return_value={'ok':True}) as check:
            for _ in range(30):self.assertEqual(self.request('POST','/api/integrations/harness/check','{}',authorized=True)[0],200)
            status,_,headers=self.request('POST','/api/integrations/harness/check','{}',authorized=True)
            self.assertEqual(status,429);self.assertEqual(check.call_count,30);self.assertEqual(headers['Retry-After'],'60')
    def test_explicit_oauth_navigation_keeps_state_validation(self):
        with patch.object(self.ai,'youtube_callback',return_value={}) as callback:
            status=self.request('GET','/api/youtube/callback?state=test',headers={'Origin':'https://accounts.google.com','Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document'})[0]
            self.assertEqual(status,200);callback.assert_called_once()
        self.assertEqual(self.request('GET','/api/youtube/callback?state=test',headers={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'no-cors','Sec-Fetch-Dest':'image'})[0],403)
    def test_private_config_paths_and_symlinks_rejected(self):
        for name in ['../outside','/etc/passwd','a/b']:
            with self.assertRaises(ValueError):self.ai.write(name,{'secret':'test'})
        target=self.root/'outside.json';target.write_text('{}');(self.ai.local/'harness.json').symlink_to(target)
        with self.assertRaises(ValueError):self.ai.read('harness')
        with self.assertRaises(ValueError):self.ai.write('harness',{})
        self.assertEqual(target.read_text(),'{}')
    def test_backup_symlink_does_not_write_outside(self):
        outside=self.root/'outside';outside.mkdir();(self.root/'.backups').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValidationError):self.store.save(self.store.read())
        self.assertEqual(list(outside.iterdir()),[])


class NetworkPolicyTests(unittest.TestCase):
    def test_public_urls_and_each_redirect_keep_platform_boundary(self):
        for bad in ['https://127.0.0.1/x','https://hdslb.com.evil.example/a','http://i0.hdslb.com/a','https://user@i0.hdslb.com/a','https://i0.hdslb.com:1234/a']:
            with self.assertRaises(ValueError):public_url(bad,['hdslb.com'])
        redirect=PublicRedirects(['hdslb.com']);request=Request('https://i0.hdslb.com/cover')
        with self.assertRaises(ValueError):redirect.redirect_request(request,None,302,'found',{},'https://127.0.0.1/private')
        self.assertEqual(redirect.redirect_request(request,None,302,'found',{},'https://i1.hdslb.com/cover').full_url,'https://i1.hdslb.com/cover')
    def test_credentials_never_follow_a_redirect(self):
        request=Request('https://api.deepseek.com/chat/completions',headers={'Authorization':'Bearer test-only'})
        with self.assertRaises(ValueError):NoRedirect().redirect_request(request,None,302,'found',{},'https://other.example/collect')
    def test_limiter_recovers_after_window(self):
        clock=[0];limiter=RateLimiter(lambda:clock[0]);self.assertTrue(limiter.allow('test',1));self.assertFalse(limiter.allow('test',1))
        clock[0]=60;self.assertTrue(limiter.allow('test',1))
