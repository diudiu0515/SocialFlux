"""Generate or verify scenario documents using the canonical catalog owner."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scenario_design.catalog import (
    assert_document_current,
    assert_manifest_current,
    discover_scenario_paths,
    write_catalog,
    write_document,
)


def main():
    parser = argparse.ArgumentParser(description="Generate paired scenario docs and catalog")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    catalog = Path("configs/scale300_v1/scenarios")
    paths = args.paths or discover_scenario_paths(catalog)
    if not paths:
        parser.error("no bundled scenario JSON files found")
    for path in paths:
        output = assert_document_current(path) if args.check else write_document(path)
        print(f"{'checked' if args.check else 'generated'} {output}")
    directories = {
        path.parent.parent if path.parent.name.startswith("scenario_") else path.parent
        for path in paths
    }
    for directory in sorted(directories):
        manifest = assert_manifest_current(directory) if args.check else None
        if not args.check:
            write_catalog(directory)
            manifest = directory / "manifest.json"
        print(f"{'checked' if args.check else 'generated'} {manifest}")
        print(f"{'checked' if args.check else 'generated'} {directory / 'coverage_matrix.json'}")


if __name__ == "__main__":
    main()
