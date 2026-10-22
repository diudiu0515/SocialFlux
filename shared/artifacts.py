"""Stable JSON artifact serialization shared by builders and audits."""

import hashlib
import json
from pathlib import Path


def atomic_json(path, value):
    """Replace a JSON artifact only after serialization and writing succeed.

    Callers own synchronization when writing the same destination concurrently.
    The UTF-8 format and temporary filename preserve the existing artifact
    contract; this helper does not change hashes or add serialization defaults.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def canonical_json_sha256(value):
    """Hash canonical JSON content, independently of a source file's layout."""
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
