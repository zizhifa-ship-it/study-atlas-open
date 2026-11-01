"""首次使用的空白资料库；AI 为替身，所有配置与资料在临时目录。"""
import json
import sys
import tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from browser_fixture import DemoAI
from server import LibraryStore, make_handler

with tempfile.TemporaryDirectory(prefix='study-atlas-community-') as folder:
    root=Path(folder);path=root/'library.json'
    path.write_text(json.dumps({'schemaVersion':1,'revision':0,'categories':[],'videos':[],'insights':[]}))
    ai=DemoAI();ai.root=root;ai.write('harness',{});ai.write('ai',{})
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(LibraryStore(path),ai))
    print('TEST_URL=http://127.0.0.1:'+str(server.server_port),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
