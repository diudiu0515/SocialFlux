"""Load fixed prompts and verify their content against the prompt manifest."""

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"
RETIRED_PATH = ROOT / "retired.json"
_PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")


def prompt_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def get_prompt(prompt_id):
    manifest = prompt_manifest()["prompts"]
    if prompt_id not in manifest:
        retired = json.loads(RETIRED_PATH.read_text(encoding="utf-8"))["prompts"]
        if prompt_id in retired:
            raise KeyError(
                f"retired prompt id: {prompt_id}; use an active configuration. "
                "Historical reproduction requires the matching archived snapshot; "
                "see docs/prompts/PROMPT_AUDIT.md. No automatic substitution."
            )
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
    unresolved = sorted(set(_PLACEHOLDER_PATTERN.findall(content)))
    if unresolved:
        raise ValueError(
            f"prompt {prompt_id} has unresolved placeholders: {unresolved}"
        )
    return content
