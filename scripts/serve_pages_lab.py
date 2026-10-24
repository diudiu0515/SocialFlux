"""Serve existing research APIs and durable annotation behind the Pages frontend."""
import argparse
import http.client
import json
import mimetypes
from pathlib import Path
import shutil
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from web.server import App


def handler_type(frontend_origin, public_origin, username, password, proxy_secret,
                 annotation_port, annotation_public, media_root):
    class PagesLab(App):
        auth_username = username
        auth_password = password
        trusted_api_origins = frozenset([frontend_origin])

        def end_headers(self):
            if self.headers.get('Origin') == frontend_origin:
                self.send_header('Access-Control-Allow-Origin', frontend_origin)
                self.send_header('Access-Control-Expose-Headers', 'Content-Disposition')
                self.send_header('Vary', 'Origin')
            super().end_headers()

        def do_OPTIONS(self):
            requested = {x.strip().lower() for x in self.headers.get('Access-Control-Request-Headers', '').split(',') if x.strip()}
            path = urlparse(self.path).path
            if (self.headers.get('Origin') != frontend_origin
                    or self.headers.get('Access-Control-Request-Method') not in {'GET', 'POST'}
                    or not (path.startswith('/api/') or path.startswith('/media/'))
                    or not requested <= {'authorization', 'content-type', 'x-annotation-recovery'}):
                self.send_json({'error': '不允许此跨站请求'}, 403)
                return
            self.send_response(204)
            self.send_header('Access-Control-Allow-Methods', 'GET, POST')
            self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, X-Annotation-Recovery')
            self.send_header('Access-Control-Max-Age', '600')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def proxy(self):
            if not self.authenticate():
                return
            origin = self.headers.get('Origin')
            if origin and origin not in {frontend_origin, public_origin} and urlparse(origin).netloc != self.headers.get('Host'):
                self.send_json({'error': '跨站请求未被允许'}, 403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 1_000_000:
                    self.send_json({'error': '内容过长'}, 413)
                    return
                headers = {'X-SocialFlux-Proxy': proxy_secret,
                           'Content-Type': self.headers.get('Content-Type', ''),
                           'X-Annotation-Recovery': self.headers.get('X-Annotation-Recovery', '')}
                connection = http.client.HTTPConnection('127.0.0.1', annotation_port, timeout=30)
                try:
                    connection.request(self.command, self.path, self.rfile.read(length) if length else None, headers)
                    response = connection.getresponse()
                    body = response.read()
                    status = response.status
                    disposition = response.getheader('Content-Disposition')
                finally:
                    connection.close()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                if disposition:
                    self.send_header('Content-Disposition', disposition)
                self.end_headers()
                self.wfile.write(body)
            except (OSError, ValueError, http.client.HTTPException):
                self.send_json({'error': '标注服务暂时不可用，输入仍保留在本设备，请稍后重试。'}, 503)

        def local_asset(self, path, root):
            if not self.authenticate():
                return
            target = (root / path).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(target.stat().st_size))
            self.send_header('Cache-Control', 'private, max-age=0')
            self.end_headers()
            with target.open('rb') as handle:
                shutil.copyfileobj(handle, self.wfile)

        def do_GET(self):
            path = urlparse(self.path).path
            if path.startswith('/api/annotation/'):
                return self.proxy()
            if path == '/annotation':
                self.send_response(302)
                self.send_header('Location', '/annotation/')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if path == '/annotation/':
                return self.local_asset('index.html', annotation_public)
            if path.startswith('/annotation/'):
                return self.local_asset(path.removeprefix('/annotation/'), annotation_public)
            if path.startswith('/media/'):
                return self.local_asset(path.removeprefix('/media/'), media_root)
            super().do_GET()

        def do_POST(self):
            if urlparse(self.path).path.startswith('/api/annotation/'):
                return self.proxy()
            super().do_POST()

    PagesLab.public_origin = public_origin
    return PagesLab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=6006)
    parser.add_argument('--username', default='socialflux')
    parser.add_argument('--password-file', type=Path, required=True)
    parser.add_argument('--proxy-secret-file', type=Path, required=True)
    parser.add_argument('--frontend-origin', required=True)
    parser.add_argument('--public-origin', required=True)
    parser.add_argument('--annotation-port', type=int, default=6067)
    parser.add_argument('--annotation-public', type=Path, required=True)
    parser.add_argument('--media-root', type=Path, required=True)
    args = parser.parse_args()
    for origin in (args.frontend_origin, args.public_origin):
        parsed = urlparse(origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            parser.error('Origins must be exact HTTPS origins')
    handler = handler_type(args.frontend_origin, args.public_origin, args.username,
                           args.password_file.read_text().strip(), args.proxy_secret_file.read_text().strip(),
                           args.annotation_port, args.annotation_public, args.media_root)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print('Pages-compatible Lab API ready', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
