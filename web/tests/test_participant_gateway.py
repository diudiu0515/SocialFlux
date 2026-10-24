import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from scripts.serve_pages_lab import handler_type


class ParticipantGatewayTests(unittest.TestCase):
    def test_public_entry_keeps_admin_and_media_protected(self):
        seen=[]
        class Storage(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(dict(self.headers))
                body=json.dumps({'session':{'id':'own'} if self.headers.get('X-Annotation-Recovery')=='test-code' else None,'invited':True}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args): pass
        store=ThreadingHTTPServer(('127.0.0.1',0),Storage)
        Thread(target=store.serve_forever,daemon=True).start()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'index.html').write_text('public entry');(root/'clip.mp4').write_bytes(b'test media')
            handler=handler_type('https://diudiu0515.github.io','https://backend.example','researcher','test-password','test-proxy',store.server_port,root,root)
            server=ThreadingHTTPServer(('127.0.0.1',0),handler);Thread(target=server.serve_forever,daemon=True).start()
            def get(path,headers=None):
                connection=http.client.HTTPConnection(*server.server_address,timeout=5)
                try:
                    connection.request('GET',path,headers=headers or {});r=connection.getresponse();r.read();return r.status
                finally:connection.close()
            try:
                self.assertEqual(get('/annotation/'),200)
                self.assertEqual(get('/api/annotation/status'),200)
                self.assertEqual(seen[-1]['X-SocialFlux-Proxy'],'test-proxy')
                self.assertEqual(get('/api/lab'),401)
                self.assertEqual(get('/api/annotation/health'),404)
                self.assertEqual(get('/api/annotation/resume'),404)
                self.assertEqual(get('/api/annotation/status',{'Origin':'https://untrusted.example'}),403)
                self.assertEqual(get('/media/clip.mp4'),401)
                self.assertEqual(get('/media/clip.mp4',{'X-Annotation-Recovery':'wrong'}),401)
                self.assertEqual(get('/media/clip.mp4',{'X-Annotation-Recovery':'test-code'}),200)
            finally:server.shutdown();server.server_close();store.shutdown();store.server_close()


if __name__=='__main__':unittest.main()
