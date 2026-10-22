"""Rebuild the bundled Noto Sans SC subset from all public content and UI text.

Usage: python scripts/subset-font.py /path/to/NotoSansSC.ttf
Requires fonttools[woff]. Keep the font's existing OFL license in public/fonts.
"""
from pathlib import Path
import json
import gzip
import base64
import sys
from fontTools import subset
from fontTools.ttLib import TTFont

root = Path(__file__).resolve().parent.parent
text = ''.join(chr(code) for code in range(32, 127))
for folder in ('app', 'lib', 'data'):
    for path in sorted((root / folder).rglob('*')):
        if path.suffix in ('.tsx', '.ts', '.json'):
            text += path.read_text() if path.suffix != '.json' else json.dumps(json.loads(path.read_text()), ensure_ascii=False)
# Server data is encoded; font glyph coverage must include the evidence shown after unlock.
server_path = root / 'data/research-server.json'
if server_path.exists():
    bundle = json.loads(gzip.decompress(base64.b64decode(json.loads(server_path.read_text())['gzip_base64'])))
    text += json.dumps(bundle, ensure_ascii=False)
    for section in ('private', 'evidence_blobs'):
        for encoded in bundle.get(section, {}).values():
            text += gzip.decompress(base64.b64decode(encoded)).decode()
for name in ('claude-calibration-server.json', 'gate2-review-server.json'):
    extra_path = root / 'data' / name
    if extra_path.exists():
        text += gzip.decompress(base64.b64decode(json.loads(extra_path.read_text())['gzip_base64'])).decode()
font = TTFont(sys.argv[1])
required = {ord(char) for char in text if not char.isspace()}
missing = required - set(font.getBestCmap())
if missing:
    raise SystemExit('Source font is missing codepoints: ' + ', '.join(f'U+{code:04X}' for code in sorted(missing)))
options = subset.Options()
options.flavor = 'woff2'
subsetter = subset.Subsetter(options=options)
subsetter.populate(text=text)
subsetter.subset(font)
font.flavor = 'woff2'
destination = root / 'public/fonts/socialflux-cjk.woff2'
font.save(destination)
assert not required - set(TTFont(destination).getBestCmap())
print(f'Covered {len(required)} codepoints; font size {destination.stat().st_size} bytes.')
