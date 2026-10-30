"""浏览器测试专用临时服务；不读取正式资料、账号或调用真实 AI。"""
import json
import base64
import tempfile
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from server import LibraryStore,make_handler
from test_practice import fixture,PracticeAI
from test_translations import TranslationAI


class DemoAI(PracticeAI):
    def __init__(self):
        super().__init__();self.translator=TranslationAI()
    def read(self,name):return self.translator.read(name)
    def write(self,name,value):self.translator.write(name,value)
    def status(self):
        return {"ai":{"mode":"harness","model":"mock-model","hasApiKey":False},"harness":{"configured":True,"model":{"model":"mock-model"}},"youtube":{"configured":False,"connected":False}}
    def harness_generate(self,prompt):
        if prompt.startswith('你在做学习笔记翻译'):return self.translator.harness_generate(prompt)
        payload=json.loads(prompt.split('资料：\n')[-1]);wrong=payload['studentAnswer']=='不知道'
        self.result.update(verdict='incorrect' if wrong else 'correct',score=15 if wrong else 90,
                           feedback='还没有解释 DHCP 的作用，需要回到模块复习。' if wrong else '正确解释了地址自动分配。',
                           missingPoints=['DHCP 自动分配 IP 地址'] if wrong else [])
        return super().harness_generate(prompt)


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='study-atlas-browser-') as tmp:
        path=Path(tmp)/'library.json';data=fixture();data['videos'][0]['knowledge']['modules'][0]['questions'].append({'question':'IP 负责什么？','answer':'跨网络寻址。'})
        name='a'*64+'.png';folder=Path(tmp)/'.local/media';folder.mkdir(parents=True)
        # 仅用于测试图文加载的 1x1 PNG，不是真实课程画面。
        (folder/name).write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+nmXcAAAAASUVORK5CYII='))
        data['videos'][0]['visuals']={'status':'ready','cover':name,'frames':[{'asset':name,'timeSec':20+i*20,'label':'测试画面','moduleId':'m1'} for i in range(3)],'message':'测试专用','createdAt':'2026-10-30'}
        path.write_text(json.dumps(data,ensure_ascii=False))
        ai=DemoAI();ai.root=Path(tmp)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(LibraryStore(path),ai))
        print('TEST_URL=http://127.0.0.1:'+str(server.server_port),flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
