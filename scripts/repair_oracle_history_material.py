"""Minimal, recorded T2 wording repairs before canonical controlled replay."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json

from offline.choice_builder import load, save, sha
from offline.oracle import ROOT, summarize
from offline.oracle_revision import repair_group
from offline.reuse_audit import digest
from providers.model_routes import ModelRoutes

RUN = ROOT / "data/offline_oracle_20261020_complete"
EDITS = {
    "GPT50_044": {
        "history": "history_b", "old": " Voters will want a direct answer.", "new": "",
        "reason": "Remove an unsupported assertion about voters' preferences; retain the same request for a legal-authorization statement.",
    },
    "GPT50_050": {
        "history": "history_a",
        "old": "that is a trust safeguard, not a claim that the network has final publication authority.",
        "new": "that is a trust safeguard; final publication authority remains with the bureau under the data-sharing memorandum.",
        "reason": "State the already-public authority allocation affirmatively; the canonical claim guard rejected the original negated wording as an affirmative claim.",
    },
}


def main():
    source = list(map(json.loads, (RUN / "source.items.jsonl").read_text().splitlines()))
    config = ModelRoutes.load(ROOT / "configs/gpt50_experiment/model_routes.hybrid.v3_2.json").provider_config("quality_review")
    config.update(timeout=120, max_transport_attempts=1, retry_backoff_seconds=0, max_tokens=7000)
    def job(scene, edit):
        original = [x for x in source if x["story_id"] == scene and x["task"] == "T2"]
        revised = deepcopy(original)
        child = RUN / "material_repairs" / scene
        amendment_path = child / "material_amendment.json"
        amendment = {"scene": scene, "kind": "controlled_history_wording_revision",
                     "original_item_hashes": [digest(x) for x in original], "edit": edit,
                     "script_sha256": sha(ROOT / "scripts/repair_oracle_history_material.py"),
                     "public_prefix_t1_unchanged": True, "source_snapshot_unchanged": True,
                     "original_failed_replay": str((RUN / "t2" / scene).relative_to(ROOT)),
                     "human_review": "pending"}
        for item in revised:
            turn = item["input"][edit["history"]][-1]
            if edit["old"] not in turn["evaluated_agent"]:
                raise ValueError("frozen wording not found")
            before = turn["evaluated_agent"]
            turn["evaluated_agent"] = before.replace(edit["old"], edit["new"], 1)
            amendment["before"], amendment["after"] = before, turn["evaluated_agent"]
        save(amendment_path, amendment)
        for item in revised:
            source_record = item["authoring"]["construction_source"]
            source_record["material_amendment"] = {"path": str(amendment_path.relative_to(ROOT)),
                                                    "sha256": sha(amendment_path)}
            source_record["history_edit"]["b_action"] = item["input"]["history_b"][-1]["evaluated_agent"]
            changes = []
            for left, right in zip(item["input"]["history_a"], item["input"]["history_b"]):
                for key in sorted((left.keys() | right.keys()) - {"turn_id"}):
                    if left.get(key) != right.get(key):
                        changes.append({"a_id": left["turn_id"], "b_id": right["turn_id"], "field": key,
                                        "before": left.get(key), "after": right.get(key)})
            item["authoring"]["history_control"]["edits"] = changes
        save(child / "revised_source_items.json", revised)
        items = repair_group(revised, child, config, "replayed_material")
        name = scene + "-T2"
        save(RUN / "groups" / name / "evidence.json", load(child / "groups" / name / "evidence.json"))
        save(RUN / "groups" / name / "items.json", items)
        return scene
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(job, scene, edit): scene for scene, edit in EDITS.items()
                   if not (RUN / "groups" / (scene + "-T2") / "items.json").exists()}
        for future in as_completed(futures):
            scene = futures[future]
            try:
                print("material repair completed", future.result(), flush=True)
            except Exception as exc:
                save(RUN / "material_repairs" / scene / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
                print("material repair FAILED", scene, type(exc).__name__, str(exc)[:300], flush=True)
            summarize(RUN)


if __name__ == "__main__":
    main()
