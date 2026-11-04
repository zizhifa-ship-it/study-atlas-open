"""Serve the compiled static site under the same subpath used by GitHub Pages."""
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PREFIX = '/study-atlas-open'
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith(PREFIX + '/'):
            self.send_error(404); return
        self.path = self.path[len(PREFIX):]
        return super().do_GET()

server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=os.environ['STUDY_ATLAS_STATIC_DIR']))
print('TEST_URL=http://127.0.0.1:' + str(server.server_port) + PREFIX + '/', flush=True)
try: server.serve_forever()
except KeyboardInterrupt: pass
finally: server.server_close()
