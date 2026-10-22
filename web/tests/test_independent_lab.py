import base64
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from scripts.build_lab_pages import build
from scripts.serve_independent_lab import handler_type


class IndependentLabTests(unittest.TestCase):
    def test_pages_artifact_has_no_data_and_uses_relative_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'site'
            page = build(output, 'https://independent.example')
            html = (page / 'index.html').read_text()
            self.assertIn('href="./experiment_hub.css"', html)
            self.assertIn('src="./lab_bootstrap.js"', html)
            self.assertIn('href="https://independent.example/offline-demo"', html)
            self.assertNotIn('seetacloud.com', html)
            self.assertNotIn('/api/lab', html)
            self.assertEqual(list(output.rglob('*.json')), [])
            self.assertNotIn('await fetch(', (page / 'experiment_hub.js').read_text())

    def test_pages_cannot_point_back_to_autodl(self):
        for url in ['https://instance.seetacloud.com:8443', 'https://instance.autodl.com',
                    'https://user:password@example.com', 'http://example.com']:
            with self.subTest(url=url), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(ValueError):
                    build(Path(temporary) / 'site', url)

    def test_hosted_cors_auth_and_migration_readiness(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin = 'https://diudiu0515.github.io'
            handler = handler_type(origin, root, 'researcher', 'test-only-password-value')
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            auth = 'Basic ' + base64.b64encode(b'researcher:test-only-password-value').decode()

            def request(method, path, headers=None, body=None):
                conn = http.client.HTTPConnection(*server.server_address, timeout=5)
                try:
                    conn.request(method, path, body=body, headers=headers or {})
                    response = conn.getresponse()
                    return response.status, dict(response.getheaders()), response.read()
                finally:
                    conn.close()

            try:
                status, _, content = request('GET', '/healthz')
                self.assertEqual(status, 200)
                self.assertIn(b'"data_ready": false', content)
                self.assertEqual(request('POST', '/api/lab/records', {'Authorization': auth}, '{}')[0], 503)
                headers = {'Origin': origin, 'Access-Control-Request-Method': 'POST',
                           'Access-Control-Request-Headers': 'authorization,content-type'}
                status, response, _ = request('OPTIONS', '/api/lab/records', headers)
                self.assertEqual(status, 204)
                self.assertEqual(response['Access-Control-Allow-Origin'], origin)
                self.assertEqual(request('OPTIONS', '/api/lab/records', {**headers, 'Origin': 'https://evil.example'})[0], 403)
                (root / 'lab-data-ready.json').write_text('{}')
                headers = {'Origin': origin, 'Sec-Fetch-Site': 'cross-site', 'Content-Type': 'application/json'}
                with patch('web.server.save_experiment_record', return_value={'id': 'test'}) as save:
                    self.assertEqual(request('POST', '/api/lab/records', headers, '{}')[0], 401)
                    self.assertEqual(request('POST', '/api/lab/records', {**headers, 'Authorization': auth}, '{}')[0], 200)
                    self.assertEqual(request('POST', '/api/lab/records', {**headers, 'Authorization': auth, 'Origin': 'https://evil.example'}, '{}')[0], 403)
                    save.assert_called_once_with({})
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
