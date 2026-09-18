#!/usr/bin/env python3
"""Fail when a repository Markdown link points to a missing local target."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"!?\[[^]\n]*\]\(([^)\n]+)\)")


def markdown_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.md"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line and (ROOT / line).exists()]


def local_target(raw: str) -> str | None:
    value = raw.strip().strip("<>")
    if not value or value.startswith(("#", "http://", "https://", "mailto:")):
        return None
    value = value.split("#", 1)[0]
    return unquote(value)


def main() -> int:
    failures: list[str] = []
    files = markdown_files()
    for source in files:
        text = source.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in LINK_RE.finditer(line):
                value = local_target(match.group(1))
                if value is None:
                    continue
                target = (source.parent / value).resolve()
                if not target.exists():
                    failures.append(
                        f"{source.relative_to(ROOT)}:{line_number}: missing {value}"
                    )
    if failures:
        print("\n".join(failures))
        return 1
    print(f"checked {len(files)} Markdown files: all local links exist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
