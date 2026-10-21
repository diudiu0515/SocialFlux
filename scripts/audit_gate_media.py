"""Gate 1 structural audit and E8 fixed-node visual screening of existing clips.

No media generation. A changed whole-scenario hash requires explicit rendering
input compatibility; frame-based visual screening never claims audio review.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
from pathlib import Path
import subprocess

from environment.delta_mapper import flatten_state
from environment.online_video_assets import build_online_asset_request
from evaluation.quality_gates import audit_scenario_gate
from evaluation.t4_media import extract_frames, video_blocks
from offline.choice_builder import load, save, sha
from offline.oracle import now
from offline.provider_compat import OfflineLoggedProvider, OfflineSamplingProvider
from offline.reuse_audit import digest
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from providers.structured import _parse_json_output
from web.live_rollouts import ROOT, ACTIVE


PROMPT = """审查合成社会互动视频与指定节点的可观察表达是否相容。人物全部是原创虚构角色。你看到四个带时间戳的视频帧，没有音频；只能评价可见线索，不能声称听到了声音，不能单凭脸推断隐藏信任或精确数字。state_context 仅解释这个节点要表达的状态方向，并非要求从图像测量私有状态。
根据实际帧检查：visible_cue_compatible（与目标表达/动作的粗粒度方向相容）、natural_and_subtle（适合普通社会对话而非夸张演出）、identity_continuity（四帧人物外观一致）、no_visible_text。每项只能 pass/fail/uncertain。说明实际可见证据和无法判断的部分。只输出JSON：
{"checks":{"visible_cue_compatible":"pass","natural_and_subtle":"pass","identity_continuity":"pass","no_visible_text":"pass"},"reason":"依据","audio_assessed":false}。
不要为了通过而忽略目标只要求轻微缓和却明显挥手/夸张表演等不匹配。"""


def prepare(run):
    original = load(ACTIVE / "preregistration.json")
    scenarios = {}
    gate1 = []
    for plan in original["plans"]:
        path = ROOT / plan["case"]["candidate"]
        if sha(path) != plan["case"]["candidate_sha256"]:
            raise ValueError("scenario changed")
        scenario = load(path)
        scenarios[scenario["scenario_id"]] = scenario
        gate1.append(audit_scenario_gate(scenario, path))
    save(run / "gate1.json", {"updated_at": now(), "scenario_count": len(gate1),
         "schema_passed": sum(r["checks"]["schema"]["status"] == "pass" for r in gate1),
         "formal_passed": sum(r["passed"] for r in gate1), "records": gate1,
         "human_review": "pending"})
    batch = ROOT / "data/gpt50/experiment"
    manifest_path = batch / "multimodal_delivery_v1/online_multimodal/manifest.json"
    manifest = load(manifest_path)
    assets = {r["media_asset_id"]: r for r in manifest["requests"]}
    candidates, gaps = [], []
    for directory in sorted(ACTIVE.glob("*GPT50_*_gpt")):
        path = next((directory / filename for filename in ("trajectory.json", "partial_trajectory.json", "checkpoint.json")
                     if (directory / filename).exists()), None)
        if not path:
            continue
        trajectory = load(path)
        for turn in trajectory.get("turns", []):
            for event in turn.get("trigger_events", []):
                row = {"scenario_id": trajectory["scenario_id"], "trajectory_id": trajectory["trajectory_id"],
                       "turn_id": turn["turn_id"], "asset_id": event.get("media_asset_id"),
                       "event_family": event.get("event_family"), "trajectory_path": str(path.relative_to(ROOT)),
                       "trajectory_sha256": sha(path)}
                asset = assets.get(row["asset_id"])
                if not asset:
                    gaps.append({**row, "reason": "asset_not_registered"})
                    continue
                video = batch / asset["video_file"]
                if not video.is_file() or not asset.get("video_sha256") or sha(video) != asset["video_sha256"]:
                    gaps.append({**row, "reason": "missing_or_unbound_video"})
                    continue
                request = load(batch / asset["request_file"])
                current = build_online_asset_request(scenarios[row["scenario_id"]], row["event_family"],
                    duration_seconds=request["duration_seconds"], reference_video_file=request.get("reference_video_file"))
                comparison = {key: request.get(key) == current.get(key) for key in (
                    "scenario_id", "event_family", "identity", "duration_seconds", "audio", "safety_check", "prompt")}
                if not all(comparison.values()):
                    gaps.append({**row, "reason": "rendering_inputs_changed", "comparison": comparison})
                    continue
                old_profile, new_profile = asset["scenario_profile_sha256"], event.get("scenario_profile_sha256")
                state = flatten_state(turn.get("state_after_public_events", turn["state_after"]))
                variable = event.get("source_state_variable")
                row.update(video_path=str(video.relative_to(ROOT)), video_sha256=sha(video),
                           source_profile_sha256=old_profile, current_profile_sha256=new_profile,
                           profile_binding="same_profile" if old_profile == new_profile else "exact_render_request_compatible",
                           render_request_sha256=digest(request), rendering_comparison=comparison,
                           observable_expression=event["observable_expression"],
                           state_context={"variable": variable, "direction": event.get("source_direction"),
                                          "value": state.get(variable)},
                           request_safety_passed=not any(request.get("safety_check", {}).values()))
                candidates.append(row)
    # Spread deterministic nodes over scenes before taking extra nodes.
    grouped = defaultdict(list)
    for row in sorted(candidates, key=lambda row: digest([row["trajectory_id"], row["turn_id"], row["asset_id"]])):
        grouped[row["scenario_id"]].append(row)
    selected = [rows[0] for _, rows in sorted(grouped.items())]
    if len(selected) < 40:
        selected += [row for rows in grouped.values() for row in rows[1:]][:40 - len(selected)]
    selected = selected[:40]
    packet = {"format": "socialflux_gate8_existing_asset_binding_v1", "manifest_path": str(manifest_path.relative_to(ROOT)),
              "manifest_sha256": sha(manifest_path), "selection": "40_scene_spread_nodes_ordered_by_stable_hash",
              "candidate_nodes": len(candidates), "selected_nodes": selected, "gaps": gaps,
              "gap_counts": dict(Counter(r["reason"] for r in gaps)),
              "profile_rebindings": sum(r["profile_binding"] != "same_profile" for r in candidates),
              "human_review": "pending"}
    frozen = run / "selection.json"
    if frozen.exists() and load(frozen) != packet:
        raise ValueError("video input selection changed")
    save(frozen, packet)
    return packet


def review_node(row, run, config):
    key = row["scenario_id"] + "-" + row["turn_id"] + "-" + row["event_family"]
    directory = run / "nodes" / key
    result_path = directory / "result.json"
    if result_path.exists():
        cached = load(result_path)
        if cached["binding"] != digest(row):
            raise ValueError("node binding changed")
        return cached
    video = ROOT / row["video_path"]
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
                           check=True, capture_output=True, text=True, timeout=30)
    metadata = json.loads(probe.stdout)
    structural = {"audio_stream_present": any(x.get("codec_type") == "audio" for x in metadata["streams"]),
                  "video_stream_present": any(x.get("codec_type") == "video" for x in metadata["streams"]),
                  "duration_seconds": float(metadata["format"]["duration"])}
    asset = {"path": str(video), "sha256": row["video_sha256"],
             "frames": extract_frames(video, run / "frames" / row["video_sha256"][:20])}
    provider = OfflineLoggedProvider(OfflineSamplingProvider(build_provider(config)), directory / "calls")
    messages = [{"role": "system", "content": PROMPT}, {"role": "user", "content": [
        {"type": "text", "text": json.dumps({k: row[k] for k in
             ("scenario_id", "event_family", "observable_expression", "state_context")}, ensure_ascii=False)},
        *video_blocks(asset, "video_frames")]}]
    for attempt in range(2):
        try:
            result = _parse_json_output(provider.complete(messages, temperature=0, max_tokens=1600))
            if (set(result["checks"]) != {"visible_cue_compatible", "natural_and_subtle", "identity_continuity", "no_visible_text"}
                    or not set(result["checks"].values()) <= {"pass", "fail", "uncertain"}
                    or result.get("audio_assessed") is not False or not result.get("reason")):
                raise ValueError("invalid visual review schema")
            record = {"binding": digest(row), "node": row, "structural": structural, "review": result,
                      "visual_screen_passed": all(x == "pass" for x in result["checks"].values()),
                      "provider": public_provider_config(config), "audio_semantics": "not_assessed_frames_only",
                      "human_review": "pending"}
            save(result_path, record)
            return record
        except Exception as exc:
            save(directory / ("failure-" + str(attempt) + ".json"), {"type": type(exc).__name__, "message": str(exc)})
            if attempt:
                raise


def report(run, packet):
    records = [load(p) for p in sorted((run / "nodes").glob("*/result.json"))]
    summary = {"human_attestation": False, "reviewers": [], "reviewed_at_utc": "", "review_status": "pending_human",
               "passed": False, "matched_node_count": len(packet["selected_nodes"]),
               "generated_video_count": len(packet["selected_nodes"]), "request_safety_passed":
                   bool(packet["selected_nodes"]) and all(r["request_safety_passed"] for r in packet["selected_nodes"]),
               "machine_reviewed_nodes": len(records), "visual_passed_nodes": sum(r["visual_screen_passed"] for r in records),
               "machine_screen_passed": len(records) >= 40 and all(r["visual_screen_passed"] for r in records),
               "llm_review_status": "completed" if len(records) == len(packet["selected_nodes"]) == 40 else "incomplete",
               "audio_semantic_review": "pending_human", "transport": "four_timestamped_visual_frames",
               "binding_method": "exact_original_and_current_render_request_comparison",
               "human_profile_rebinding_approval": "pending"}
    save(run / "video_state_consistency.json", {"format": "socialflux_environment_video_state_consistency_v1",
         "updated_at": now(), "record": summary, "review_items": records,
         "selection_path": str((run / "selection.json").relative_to(ROOT))})
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/gate_media_machine_20261020")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    run = ROOT / args.output
    packet = prepare(run)
    if args.prepare_only:
        print(json.dumps({"candidate_nodes": packet["candidate_nodes"], "selected": len(packet["selected_nodes"]),
                          "gaps": packet["gap_counts"], "profile_rebindings": packet["profile_rebindings"]}))
        return
    config = ModelRoutes.load(ROOT / "configs/gpt50_experiment/model_routes.hybrid.v3_2.json").provider_config("quality_review")
    config.update(timeout=100, max_transport_attempts=1, retry_backoff_seconds=0)
    save(run / "freeze.json", {"code_sha256": sha(Path(__file__)), "prompt_sha256": digest(PROMPT),
                              "provider": public_provider_config(config), "selection_sha256": sha(run / "selection.json")})
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(review_node, row, run, config): row for row in packet["selected_nodes"]}
        for future in as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
                print(row["scenario_id"], row["turn_id"], result["review"]["checks"], flush=True)
            except Exception as exc:
                print(row["scenario_id"], "FAILED", type(exc).__name__, str(exc)[:180], flush=True)
            report(run, packet)
    print(json.dumps(report(run, packet)), flush=True)


if __name__ == "__main__":
    main()
