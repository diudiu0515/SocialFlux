"""Add a durable server receipt to the existing version-aware human summary."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from web.human_gt import import_receipt

if __name__ == '__main__':
    path = Path(sys.argv[1]).resolve()
    if not path.is_relative_to(ROOT / 'data/sites_annotation/receipts'):
        raise SystemExit('Receipt must be inside the private portable annotation archive')
    import_receipt(json.loads(path.read_text()))
    print('Receipt added to version-aware summary')
