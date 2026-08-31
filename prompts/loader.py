"""Load fixed prompts and verify their content against the prompt manifest."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"


def prompt_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def get_prompt(prompt_id):
    manifest = prompt_manifest()["prompts"]
    if prompt_id not in manifest:
        raise KeyError(f"unknown prompt id: {prompt_id}")
    entry = manifest[prompt_id]
    path = ROOT / entry["path"]
    content = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(f"prompt checksum mismatch: {prompt_id}")
    return content


def render_prompt(prompt_id, payload=None, **values):
    values = dict(values)
    if payload is not None:
        values["payload_json"] = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    content = get_prompt(prompt_id)
    for key, value in values.items():
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
        content = content.replace("{{" + key + "}}", rendered)
    return content
