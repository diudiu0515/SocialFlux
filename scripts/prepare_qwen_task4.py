#!/usr/bin/env python3
"""Freeze the Qwen Task4 runtime and scenario catalog before starting a run."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.qwen_task4 import DEFAULT_CONFIG, digest, load_config, load_prompt_profile
from shared.artifacts import atomic_json


def prepare(output, preregistration, config_path=DEFAULT_CONFIG):
    output = Path(output).resolve()
    config = load_config(config_path)
    load_prompt_profile(config)
    # A new run never overwrites a frozen run or resumes failed episodes.
    output.mkdir(parents=True, exist_ok=False)
    runtime = output / "runtime"
    runtime.mkdir()
    files = {}
    for folder in ("environment", "providers", "pipeline", "policies", "rollout", "memory",
                   "shared", "tasks", "evaluation", "prompts", "schemas", "offline", "scenario_design"):
        for source in sorted((ROOT / folder).rglob("*")):
            if source.is_file() and source.suffix in {".py", ".json", ".md", ".txt"}:
                files[str(source.relative_to(ROOT))] = source
    for relative in ("scripts/serve_qwen_task4.py", "scripts/prepare_qwen_task4.py",
                     "configs/state_trust_current_evidence_v1.json"):
        files[relative] = ROOT / relative
    files["configs/qwen_task4/environment.json"] = Path(config_path)
    for relative, source in files.items():
        target = runtime / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    inputs = output / "inputs"
    inputs.mkdir()
    plans = json.loads(Path(preregistration).read_text())["plans"]
    catalog = {"scenarios": {}}
    for plan in plans:
        case = plan["case"]
        sid = case["scenario_id"]
        source = ROOT / case["candidate"]
        sha = digest(source)
        if sid in catalog["scenarios"]:
            if catalog["scenarios"][sid]["sha256"] != sha:
                raise ValueError("Conflicting scenario versions: " + sid)
            continue
        scenario = json.loads(source.read_text())
        if scenario["scenario_id"] != sid:
            raise ValueError("Scenario ID mismatch: " + sid)
        target = inputs / (sha + ".json")
        shutil.copy2(source, target)
        catalog["scenarios"][sid] = {"path": str(target), "sha256": sha}
    if not catalog["scenarios"]:
        raise ValueError("Empty scenario catalog")
    atomic_json(output / "catalog.json", catalog)
    manifest = {
        "profile": config["profile"], "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": str(runtime), "config": config,
        "runtime_sha256": {relative: digest(runtime / relative) for relative in files},
        "scenario_catalog_sha256": digest(output / "catalog.json"),
        "scenario_source_sha256": digest(preregistration),
        "scenario_count": len(catalog["scenarios"]),
        "formal_admission": False, "human_review_status": "pending",
        "reward_status": "unconfigured",
        "isolation": "Explicit Qwen entry only. Existing GPT/Claude paths are unchanged.",
    }
    atomic_json(output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    manifest = prepare(args.output, args.preregistration, args.config)
    print(json.dumps({"runtime": manifest["runtime"], "scenario_count": manifest["scenario_count"]}))


if __name__ == "__main__":
    main()
