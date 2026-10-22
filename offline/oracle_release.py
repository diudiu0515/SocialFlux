"""Publish fully checked oracle candidates, preserving evidence and human status."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil

from offline.choice_builder import load, save, save_text, sha, write_bundle
from offline.oracle import ROOT, BANK, bound_source, summarize, validate_t2_replay, now
from offline.reuse_audit import digest
from tasks.offline_choice import public_instance, validate_item
from tasks.offline_design import grouped_record

RUN = ROOT / "data/offline_oracle_20261020_complete"
LETTER = re.compile(r"(?<![A-Za-z0-9_])[ABCD](?![A-Za-z0-9_:])")


def verify_amendment(original, current):
    """Only the recorded historical action may change; all other input is frozen."""
    if original["input"] == current["input"]:
        return False
    record = current["authoring"]["construction_source"].get("material_amendment")
    if current["task"] != "T2" or not record:
        raise ValueError("unregistered public material change")
    path = (ROOT / record["path"]).resolve()
    if ROOT not in path.parents or sha(path) != record["sha256"]:
        raise ValueError("material amendment hash mismatch")
    amendment = load(path)
    if digest(original) not in amendment["original_item_hashes"]:
        raise ValueError("material amendment source mismatch")
    expected = deepcopy(original["input"])
    turn = expected[amendment["edit"]["history"]][-1]
    if turn["evaluated_agent"] != amendment["before"]:
        raise ValueError("material amendment action mismatch")
    turn["evaluated_agent"] = amendment["after"]
    if expected != current["input"]:
        raise ValueError("public changes exceed frozen amendment")
    return True


def relabel_rationale(text, mapping, option_positions):
    positions = {m.start(): m.group() for m in LETTER.finditer(text)}
    if not set(option_positions) <= positions.keys():
        raise ValueError("unknown option reference position")
    chars = list(text)
    for pos in option_positions:
        chars[pos] = mapping[positions[pos]]
    return "".join(chars)


def normalize_rationales(item, run):
    author = item["authoring"]
    artifact = load(ROOT / author["generation_source"]["path"])
    data = artifact.get("result", artifact)
    proposal = next(q for q in data["questions"] if q["instance_id"] == item["instance_id"])
    shift = ("ABCD".index(author["answer"]) - "ABCD".index(proposal["answer"])) % 4
    mapping = {c: "ABCD"[(n + shift) % 4] for n, c in enumerate("ABCD")}
    if not shift:
        return
    audit = {"mapping": mapping, "original_proposal_sha256": digest(proposal), "fields": {}}
    for key, destination in (("rationale", author), ("oracle_rationale", author["oracle_reference"])):
        text = proposal[key]
        positions = [m.start() for m in LETTER.finditer(text)]
        if not positions:
            continue
        if item["task"] == "T2":
            path = run / "option_references" / (item["instance_id"] + "-" + key + ".json")
            classified = load(path)
            if classified["text_sha256"] != digest(text):
                raise ValueError("option reference classification is stale")
            positions = classified["option_positions"]
            audit["fields"][key] = {"source": str(path.relative_to(ROOT)), "sha256": sha(path)}
        else:
            audit["fields"][key] = {"rule": "standalone option letters in T1/T3; actions have numeric labels"}
        destination["rationale"] = relabel_rationale(text, mapping, positions)
    author["option_reference_normalization"] = audit


def publish(run=RUN):
    summary, items = summarize(run)
    if any(summary[k] != 300 for k in ("authored_items", "independently_checked_items", "public_blind_checked_items")):
        raise ValueError("300 authored, private-checked and blind-checked items required")
    originals = {x["instance_id"]: x for x in map(json.loads, (run / "source.items.jsonl").read_text().splitlines())}
    import jsonschema
    schema = jsonschema.Draft202012Validator(load(ROOT / "schemas/offline_choice_item_v2.schema.json"))
    amendments = []
    for item in items:
        if verify_amendment(originals[item["instance_id"]], item):
            amendments.append(item["instance_id"])
        normalize_rationales(item, run)
        validate_item(item)
        schema.validate(item)
        ref = item["authoring"]["oracle_reference"]
        packet = load(ROOT / ref["packet_path"])
        if sha(ROOT / ref["packet_path"]) != ref["packet_sha256"] or packet["public_input"] != item["input"]:
            raise ValueError("oracle packet binding mismatch")
        if not set(item["target_spec"]["target_state_ids"]) <= set(packet["allowed_state_paths"]):
            raise ValueError("unrecorded target state")
        if item["task"] == "T2":
            source = item["authoring"]["construction_source"]
            validate_t2_replay(item, bound_source(source, "trajectory"), bound_source(source, "replay"))
    if Counter(x["authoring"]["answer"] for x in items) != Counter(dict.fromkeys("ABCD", 75)):
        raise ValueError("answer balance changed")
    summary.update(t2_replay_groups=50, material_amended_items=amendments,
                   source_state_coverage_verified=True, human_verified_items=0, formal_admitted_items=0)
    archive = run / "previous_release"
    if not archive.exists():
        shutil.copytree(BANK, archive)
    media = load(archive / "media.json")
    pairs = []
    index = {x["instance_id"]: x for x in items}
    for previous in map(json.loads, (archive / "paired.items.jsonl").read_text().splitlines()):
        identity = previous["metadata"]["modality_pair_id"]
        current = deepcopy(index[identity])
        if identity in amendments:
            assets = media.get(identity + "-video", [])
            if not assets or any(not a["evidence_ids"] or not set(a["evidence_ids"]) <= {"A:t1", "B:t1"} for a in assets):
                raise ValueError("revised T2 may reuse only unchanged shared-prefix media")
            for key in ("history_a", "history_b"):
                if current["input"][key][:-1] != originals[identity]["input"][key][:-1]:
                    raise ValueError("media-associated prefix changed")
        current.update(instance_id=previous["instance_id"], modality=previous["modality"])
        current["metadata"]["modality_pair_id"] = identity
        for key in ("media_manifest", "media_human_review", "matched_assets"):
            if key in previous["authoring"]:
                current["authoring"][key] = previous["authoring"][key]
        pairs.append(current)
    stage = run / "release"
    stage.mkdir(exist_ok=True)
    for path in archive.iterdir():
        if path.is_file():
            shutil.copyfile(path, stage / path.name)
    manifest = write_bundle(items, stage)
    manifest.update({k: v for k, v in load(archive / "manifest.json").items() if k not in manifest})
    manifest.update(format="socialflux_offline_choice_v2", oracle_run=str(run.relative_to(ROOT)),
                    oracle_summary=summary, machine_flagged_ids=summary["machine_concern_ids"],
                    blind_reviewed_items=300, modality_pairs=len(pairs) // 2)
    save(stage / "manifest.json", manifest)
    for name, rows in (("records.jsonl", [grouped_record(x) for x in items]),
                       ("paired.items.jsonl", pairs), ("paired.public.jsonl", [public_instance(x) for x in pairs])):
        save_text(stage / name, "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))
    # All schema, source, replay and media checks precede any change to the website bank.
    for path in stage.iterdir():
        if path.is_file():
            temporary = BANK / (path.name + ".publishing")
            shutil.copyfile(path, temporary)
            temporary.replace(BANK / path.name)
    save(run / "progress.json", summary)
    save(run / "published.json", {"at": now(), "items_sha256": sha(BANK / "items.jsonl"),
                                 "release_code_sha256": sha(Path(__file__)), "summary": summary})
    return summary


if __name__ == "__main__":
    print(json.dumps(publish(), ensure_ascii=False))
