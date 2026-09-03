#!/usr/bin/env python3
"""Rebuild the fixed-prompt catalog from versioned Markdown files."""

import hashlib
import json
from pathlib import Path
import re

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
VERSION = re.compile(r"_v(?P<version>\d+)$")


def build_manifest():
    prompts = {}
    for path in sorted(PROMPT_DIR.glob("*.md")):
        match = VERSION.search(path.stem)
        if not match:
            raise ValueError(f"prompt filename must end in _vN: {path.name}")
        prompts[path.stem] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "version": f"v{match.group('version')}",
        }
    return {"format": "socialflux_prompt_manifest_v2", "prompts": prompts}


def main():
    manifest = build_manifest()
    target = PROMPT_DIR / "manifest.json"
    target.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"registered {len(manifest['prompts'])} prompts in {target}")


if __name__ == "__main__":
    main()
