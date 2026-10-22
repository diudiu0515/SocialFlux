"""Build the GitHub Pages Lab frontend; private data remains on its own backend."""
import argparse
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def build(output, backend_url, allow_loopback=False):
    parsed = urlparse(backend_url)
    local = allow_loopback and parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1'}
    if ((parsed.scheme != 'https' and not local) or not parsed.hostname or parsed.username
            or parsed.password or parsed.path.strip('/') or parsed.query or parsed.fragment):
        raise ValueError('Provide the independent backend HTTPS origin, without credentials or path')
    if 'autodl' in parsed.hostname.lower() or parsed.hostname.lower().endswith('seetacloud.com'):
        raise ValueError('The Pages deployment must not depend on AutoDL')
    backend_url = backend_url.rstrip('/')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory must be empty')
    page = output / 'lab'
    page.mkdir(parents=True)
    static = ROOT / 'web/static'
    html = (static / 'experiment_hub.html').read_text()
    html = html.replace('href="/experiment_hub.css"', 'href="./experiment_hub.css"')
    html = html.replace('href="/lab"', 'href="./"')
    html = re.sub(r'href="(/[^"\n]+)"', lambda match: 'href="' + backend_url + match[1] + '"', html)
    html = html.replace('连接本地实验目录', '连接实验数据')
    html = html.replace('<script src="/experiment_hub.js"></script>',
                        '<script src="./lab-config.js"></script><script src="./lab_bootstrap.js"></script><script src="./experiment_hub.js"></script>')
    (page / 'index.html').write_text(html)
    script = (static / 'experiment_hub.js').read_text()
    if script.count('await fetch(') != 2:
        raise ValueError('Review frontend API calls before changing the backend adapter')
    script = script.replace("'use strict';", "'use strict';\nconst labFetch = window.socialfluxLabRequest;", 1)
    script = script.replace('await fetch(', 'await labFetch(')
    (page / 'experiment_hub.js').write_text(script)
    (page / 'experiment_hub.css').write_text((static / 'experiment_hub.css').read_text().replace('/fonts/', './fonts/'))
    (page / 'lab-config.js').write_text('window.SOCIALFLUX_BACKEND_URL = ' + json.dumps(backend_url) + ';\n')
    shutil.copy2(ROOT / 'web/pages/lab_bootstrap.js', page / 'lab_bootstrap.js')
    shutil.copytree(static / 'fonts', page / 'fonts')
    (output / '.nojekyll').touch()
    (output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=./lab/"><a href="./lab/">打开 Lab</a>')
    return page


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--backend-url', required=True)
    parser.add_argument('--allow-loopback', action='store_true')
    args = parser.parse_args()
    print(build(args.output, args.backend_url, args.allow_loopback))
