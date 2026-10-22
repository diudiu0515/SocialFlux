#!/usr/bin/env python3
"""Export the selected public multimodal review package with verified bindings.

The source bank remains private. Only tasks.offline_choice.public_instance output
and explicitly selected video fields enter the participant package. Source video
bytes are copied unchanged to SHA-only filenames; this script never transcodes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tasks.offline_choice import public_instance, visible_evidence

RELEASE = "offline-multimodal-review-20261021-v1"
EXPECTED_BANK_SHA256 = "c1d1f3fd60e94e0c09e1b6ecae4187cd3ae98a7b32e836204749d7de559deee8"
EXPRESSION_KEYS = {"facial_expression", "gaze", "speech_style", "prosody", "behavioral_cues"}
FORBIDDEN_KEYS = {
    "authoring", "answer", "acceptable_answers", "ground_truth", "oracle_state",
    "oracle_reference", "initial_state", "persona", "private_state", "private_states",
    "future_turns", "target_spec", "analysis", "branch_evidence", "source_binding",
    "scenario_source", "provider", "path", "source_path", "trajectory_path",
    "human_review", "speech_verified", "speech_screen", "asr", "review_status",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def expression(value):
    require(isinstance(value, dict) and set(value) <= EXPRESSION_KEYS,
            "Unexpected observable expression field")
    return deepcopy(value)


def assert_public_boundary(value):
    if isinstance(value, dict):
        require(not set(value) & FORBIDDEN_KEYS, "Private metadata entered participant package")
        for child in value.values():
            assert_public_boundary(child)
    elif isinstance(value, list):
        for child in value:
            assert_public_boundary(child)
    elif isinstance(value, str):
        require("/root/" not in value and "file://" not in value,
                "Filesystem source path entered participant package")


def turns_by_id(item):
    result = {}
    for group in ("history", "history_a", "history_b"):
        for turn in item["input"].get(group, []):
            require(turn["turn_id"] not in result, "Duplicate public evidence ID")
            result[turn["turn_id"]] = turn
    if item["input"].get("shared_ending"):
        turn = item["input"]["shared_ending"]
        require(turn["turn_id"] not in result, "Duplicate shared-ending ID")
        result[turn["turn_id"]] = turn
    return result


def export(site_dir, report_path, *, expected_bank_sha256=EXPECTED_BANK_SHA256, release=RELEASE):
    bank_dir = ROOT / "tasks/examples/offline_scenarios_v2"
    bank_path = bank_dir / "items.jsonl"
    bank_sha = file_sha256(bank_path)
    require(bank_sha == expected_bank_sha256, "Source bank has changed")
    talking_dir = ROOT / "data/offline_talking_head_en_v1" / bank_sha[:16]
    bank_manifest = load(bank_dir / "manifest.json")
    media = load(bank_dir / "media.json")
    manifest = load(talking_dir / "manifest.json")
    completed = load(talking_dir / "completed_nodes.json")
    selection = load(talking_dir / "preview_selection.json")
    for source in (bank_manifest, manifest, selection):
        require(source["items_sha256"] == bank_sha, "Manifest bank SHA mismatch")
    require(manifest["speech_language"] == selection["speech_language"] == "en",
            "Selected talking-head batch is not English")
    rows = [json.loads(line) for line in bank_path.read_text(encoding="utf-8").splitlines() if line]
    item_by_id = {item["instance_id"]: item for item in rows}
    require(len(rows) == len(item_by_id) == 300, "Unexpected bank size or duplicate IDs")
    item_hashes = {key: canonical_sha256(item) for key, item in item_by_id.items()}
    legacy_path = site_dir / "data/questions.json"
    legacy_sha = file_sha256(legacy_path)

    assets = {}
    sources = {}
    source_checks = []
    verified_sources = set()
    included_ids = set()

    def register(asset, scene_id, kind, speaker, label, spoken_text, source_text, observable):
        sha = asset["sha256"]
        require(re.fullmatch(r"[0-9a-f]{64}", sha) is not None, "Malformed asset SHA")
        source = Path(asset["path"])
        if not source.is_absolute():
            source = ROOT / source
        else:
            # A staged English release keeps final workspace paths in bindings.
            # Prefer the corresponding staged bytes when validating that release.
            try:
                relative = source.relative_to(Path(__file__).resolve().parents[1])
            except ValueError:
                pass
            else:
                if (ROOT / relative).is_file():
                    source = ROOT / relative
        require(source.is_file() and source.suffix == ".mp4", "Missing MP4 source")
        identity = (str(source.resolve()), sha)
        if identity not in verified_sources:
            require(file_sha256(source) == sha, "Video source SHA mismatch")
            verified_sources.add(identity)
        public = {
            "asset_id": "video-" + sha[:16], "sha256": sha,
            "url": "/media/" + sha + ".mp4", "scene_id": scene_id, "kind": kind,
            "speaker": speaker, "label": label, "spoken_text": spoken_text,
            "source_text": source_text, "observable_expression": expression(observable),
            "bindings": [],
        }
        if sha in assets:
            require({k: v for k, v in assets[sha].items() if k != "bindings"}
                    == {k: v for k, v in public.items() if k != "bindings"},
                    "Inconsistent metadata for shared video SHA")
        else:
            assets[sha] = public
            sources[sha] = source
        return assets[sha]

    def add_binding(video, item, evidence_ids):
        require(evidence_ids and len(evidence_ids) == len(set(evidence_ids)),
                "Missing or duplicate evidence binding")
        require(set(evidence_ids) <= visible_evidence(item), "Binding cites invisible evidence")
        require(item["story_id"] == video["scene_id"], "Binding crosses scenes")
        binding = {"instance_id": item["instance_id"], "evidence_ids": list(evidence_ids)}
        require(binding not in video["bindings"], "Duplicate asset-item binding")
        video["bindings"].append(binding)
        included_ids.add(item["instance_id"])

    require(len(media) == 270, "Unexpected nonverbal binding count")
    for video_item_id, media_assets in sorted(media.items()):
        require(video_item_id.endswith("-video"), "Unexpected media instance ID")
        instance_id = video_item_id.removesuffix("-video")
        require(instance_id in item_by_id and len(media_assets) == 1,
                "Unknown or ambiguous nonverbal media binding")
        item = item_by_id[instance_id]
        source_asset = media_assets[0]
        require(source_asset["response_neutral"] is True, "Nonverbal video has verbal response")
        require(source_asset["source_asset_id"].split(":")[0] == item["story_id"],
                "Nonverbal source scene mismatch")
        source_binding = source_asset["source_binding"]
        require(source_binding["trajectory_sha256"]
                == item["authoring"]["construction_source"]["trajectory_sha256"],
                "Nonverbal trajectory binding mismatch")
        turns = turns_by_id(item)
        evidence_ids = source_asset["evidence_ids"]
        require(evidence_ids and set(evidence_ids) <= turns.keys(), "Missing nonverbal turn")
        observed = expression(turns[evidence_ids[0]]["observable_expression"])
        for evidence_id in evidence_ids:
            require(evidence_id.split(":")[-1] == source_binding["turn_id"],
                    "Nonverbal evidence turn mismatch")
            require(expression(turns[evidence_id]["observable_expression"]) == observed,
                    "Nonverbal expression changes across bound evidence")
        video = register(source_asset, item["story_id"], "nonverbal",
                         item["input"]["target_character"]["name"],
                         "Nonverbal history clip" if bank_manifest.get('language') == 'en' else "非语言前史片段", None, None, observed)
        add_binding(video, item, evidence_ids)

    node_by_id = {node["node_id"]: node for node in manifest["nodes"]}
    completed_by_id = {node["node_id"]: node for node in completed}
    require(len(node_by_id) == len(manifest["nodes"]) == 7, "Unexpected manifest nodes")
    require(len(completed_by_id) == len(completed) == 7, "Unexpected completed nodes")
    require(len(selection["node_ids"]) == 7
            and set(selection["node_ids"]) == set(node_by_id) == set(completed_by_id),
            "Selected and completed nodes differ")
    require(set(selection["scene_ids"]) == {node["scenario_id"] for node in node_by_id.values()},
            "Selected scene list differs from manifest")
    require(set(selection["request_ids"]) == {request["request_id"] for request in manifest["requests"]},
            "Selected requests differ from current manifest")
    for node_id in selection["node_ids"]:
        node = node_by_id[node_id]
        complete = completed_by_id[node_id]
        source_asset = complete["asset"]
        require(source_asset["source_asset_id"] == node_id, "Completed asset ID mismatch")
        require(source_asset["media_kind"] == "talking_head", "Unexpected completed media kind")
        require(source_asset["speech_language"] == node["speech_language"] == "en",
                "Completed video language mismatch")
        for key in ("spoken_text", "source_public_response"):
            require(source_asset[key] == node[key], "Completed text differs from selected text")
        require(complete["bindings"] == node["bindings"], "Completed item bindings have changed")
        require(set(node["segment_request_ids"]) <= set(selection["request_ids"]),
                "Node includes an unselected request")
        require({edit["request_id"] for edit in source_asset["boundary_silence_edits"]}
                == set(node["segment_request_ids"]), "Completed asset uses superseded requests")
        video = register(source_asset, node["scenario_id"], "talking_head", node["speaker"]["name"],
                         "English dialogue sample" if bank_manifest.get('language') == 'en' else "英文对话样片", node["spoken_text"], node["source_public_response"],
                         node["source_observable_expression"])
        for binding in node["bindings"]:
            item = item_by_id[binding["instance_id"]]
            require(item_hashes[item["instance_id"]] == binding["item_sha256"],
                    "Talking-head item SHA mismatch")
            require(item["input"]["target_character"] == node["speaker"], "Speaker binding mismatch")
            for evidence_id in binding["evidence_ids"]:
                turn = turns_by_id(item)[evidence_id]
                require(turn.get("current_response", turn.get("environment_character")) == node["source_public_response"],
                        "Talking-head text differs from bound public evidence")
                require(expression(turn["observable_expression"]) == video["observable_expression"],
                        "Talking-head expression differs from bound public evidence")
            add_binding(video, item, binding["evidence_ids"])

    videos = sorted(assets.values(), key=lambda video: (video["scene_id"], video["kind"] == "talking_head", video["sha256"]))
    require(Counter(video["kind"] for video in videos) == {"nonverbal": 45, "talking_head": 7},
            "Unexpected video counts")
    require(len({video["asset_id"] for video in videos}) == 52, "Asset ID prefix collision")
    items = [{"item_sha256": item_hashes[key], "scene_id": item_by_id[key]["story_id"],
              "task": item_by_id[key]["task"], "public": public_instance(item_by_id[key])}
             for key in sorted(included_ids)]
    require(len(items) == 270, "Unexpected participant question count")
    scenes = [{"scene_id": scene_id,
               "question_ids": [row["public"]["instance_id"] for row in items if row["scene_id"] == scene_id],
               "video_ids": [video["asset_id"] for video in videos if video["scene_id"] == scene_id]}
              for scene_id in sorted({video["scene_id"] for video in videos})]
    require(len(scenes) == 45 and all(len(scene["question_ids"]) == 6 for scene in scenes),
            "Unexpected scene coverage")
    package = {"release": release, "source_bank_sha256": bank_sha,
               "items": items, "videos": videos, "scenes": scenes}
    assert_public_boundary(package)
    package["dataset_sha256"] = canonical_sha256(package)

    media_dir = site_dir / "public/media"
    expected_names = {video["sha256"] + ".mp4" for video in videos}
    media_dir.mkdir(parents=True, exist_ok=True)
    require(not {path.name for path in media_dir.iterdir()} - expected_names,
            "Unexpected pre-existing file in participant media directory")
    for video in videos:
        sha = video["sha256"]
        destination = media_dir / (sha + ".mp4")
        if not destination.exists():
            shutil.copyfile(sources[sha], destination)
        require(file_sha256(destination) == sha, "Exported video SHA mismatch")
        source_checks.append({"asset_id": video["asset_id"], "sha256": sha,
                              "bytes": destination.stat().st_size, "source_verified": True,
                              "destination_verified": True, "transcoded": False})
    output = site_dir / "data/multimodal.json"
    write_json(output, package)
    reread = load(output)
    dataset_sha = reread.pop("dataset_sha256")
    require(canonical_sha256(reread) == dataset_sha, "Written dataset canonical SHA mismatch")
    require(file_sha256(legacy_path) == legacy_sha, "Legacy question release changed")
    report = {
        "release": release, "dataset_sha256": dataset_sha, "source_bank_sha256": bank_sha,
        "output": str(output.relative_to(ROOT) if output.is_relative_to(ROOT) else output),
        "media_directory": str(media_dir.relative_to(ROOT) if media_dir.is_relative_to(ROOT) else media_dir),
        "counts": {"source_bank_items": len(rows), "items": len(items), "scenes": len(scenes),
                   "videos": len(videos), "nonverbal": 45, "talking_head": 7,
                   "bindings": sum(len(video["bindings"]) for video in videos)},
        "public_boundary": {
            "question_export": "tasks.offline_choice.public_instance allowlist",
            "video_export": "Explicit participant video fields only; source filenames replaced by SHA256",
            "forbidden_fields_scan_passed": True, "original_modality_preserved": True,
            "private_answers_states_paths_provider_and_asr_metadata_exported": False,
        },
        "verification": {"bank_sha256": True, "selection_and_completed_nodes": True,
                         "item_sha256_bindings": True, "visible_evidence_bindings": True,
                         "source_trajectory_bindings": True, "source_and_destination_video_sha256": True,
                         "canonical_dataset_sha256": True, "legacy_questions_unchanged": True},
        "legacy_questions_sha256": legacy_sha,
        "total_video_bytes": sum(row["bytes"] for row in source_checks),
        "largest_video_bytes": max(row["bytes"] for row in source_checks),
        "assets": source_checks,
        "notes": ["Seven English samples are the current selected completed nodes only.",
                  "English samples cover selected shared endings; full spoken histories remain incomplete.",
                  "Video source bytes are copied unchanged. Nonverbal clips remain tied to their original evidence IDs.",
                  "Thirty bank items without a selected video are outside this participant release.",
                  "No human review or speech-screen verdict is included in participant data."],
    }
    write_json(report_path, report)
    print(json.dumps({key: report[key] for key in ("output", "dataset_sha256", "counts", "total_video_bytes", "largest_video_bytes")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, default=ROOT / "build/annotation-demo-site")
    parser.add_argument("--report", type=Path, default=ROOT / "build/participant_multimodal_export.json")
    parser.add_argument("--expected-bank-sha256", default=EXPECTED_BANK_SHA256)
    parser.add_argument("--release", default=RELEASE)
    args = parser.parse_args()
    export(args.site_dir.resolve(), args.report.resolve(),
           expected_bank_sha256=args.expected_bank_sha256, release=args.release)
