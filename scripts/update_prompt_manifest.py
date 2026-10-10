#!/usr/bin/env python3
"""Rebuild the fixed-prompt catalog from versioned Markdown files."""

import argparse
import hashlib
import json
from pathlib import Path
import re

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
VERSION = re.compile(r"_v(?P<version>\d+)(?:_(?P<label>[a-z0-9_]+))?$")


def build_manifest():
    prompts = {}
    retired = json.loads((PROMPT_DIR / "retired.json").read_text(encoding="utf-8"))["prompts"]
    for path in sorted(PROMPT_DIR.glob("*.md")):
        if path.stem in retired:
            raise ValueError(f"retired prompt must not be re-registered: {path.stem}")
        match = VERSION.search(path.stem)
        if not match:
            raise ValueError(f"prompt filename must end in _vN or _vN_label: {path.name}")
        label = match.group("label")
        prompts[path.stem] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "version": f"v{match.group('version')}" + (f"-{label.replace('_', '-')}" if label else ""),
        }
    return {"format": "socialflux_prompt_manifest_v2", "prompts": prompts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without rewriting the manifest")
    args = parser.parse_args()
    manifest = build_manifest()
    target = PROMPT_DIR / "manifest.json"
    if args.check:
        if json.loads(target.read_text(encoding="utf-8")) != manifest:
            raise SystemExit("prompt manifest is stale; run scripts/update_prompt_manifest.py")
        print(f"verified {len(manifest['prompts'])} prompts in {target}")
        return
    target.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"registered {len(manifest['prompts'])} prompts in {target}")


if __name__ == "__main__":
    main()
