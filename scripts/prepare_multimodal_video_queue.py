#!/usr/bin/env python3
"""Adapt public renderings and prepare offline important-node video requests."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.validate import validate_scenario, validate_trajectory
from environment.video_requests import (
    TALKING_HEAD_PROMPT_ID,
    build_video_request,
)
from prompts.loader import render_prompt
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from providers.structured import (
    StructuredOutputError,
    _parse_json_output,
    complete_json,
)
from scripts.audit_formal_rollout_pool import load_records
from scripts.run_environment_interventions import load_actual_scenarios


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "multimodal_generation.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def continuity_references_from_manifest(path):
    manifest = load(path)
    references = {}
    for record in manifest.get("requests") or []:
        if record.get("dependency_phase") != 0:
            continue
        scenario_id = record.get("scenario_id")
        video_file = record.get("video_file")
        if not scenario_id or not video_file:
            raise ValueError("continuity anchor requires scenario_id and video_file")
        if scenario_id in references:
            raise ValueError(f"duplicate continuity anchor: {scenario_id}")
        references[scenario_id] = video_file
    if not references:
        raise ValueError("continuity manifest contains no anchor requests")
    return references


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


VIDEO_RENDERING_ADAPTATION_PROMPT_ID = "video_public_rendering_adaptation_v1"
VIDEO_PUBLIC_LINE_COMPRESSION_PROMPT_ID = "video_public_line_compression_v2"
_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ENGLISH_WORD = re.compile(
    r"\d+(?::\d+)+|[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*"
)
_OBSERVABLE_CUE = re.compile(
    r"\b(?:nod|blink|breath|breathe|pause|brow|gaze|eye|head|posture|lean|"
    r"shoulder|hand|mouth|lip|still|movement|exhale|inhale|swallow|shift|"
    r"tilt|look|glance|turn|lower|raise|hold|relax|tense|settle|straighten|"
    r"recoil|withdraw|move|motion|tap|touch|point|gesture|reach|press|rest|"
    r"clasp|lift)(?:s|es|ed|d|ing)?\b|\b(?:held|withdrew)\b",
    re.IGNORECASE,
)


def rendering_payload(response, expression):
    return {
        "public_response": str(response).strip(),
        "observable_expression": expression,
    }


def rendering_key(payload):
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def provider_request_count(provider):
    value = getattr(provider, "_request_count", None)
    if value is None:
        value = getattr(provider, "_call_index", 0)
    return int(value or 0)


def validate_public_rendering(value):
    if set(value) != {"english_spoken_line", "observable_expression"}:
        raise ValueError("video rendering adaptation returned unexpected keys")
    line = str(value["english_spoken_line"]).strip()
    words = _ENGLISH_WORD.findall(line)
    if _CJK_PATTERN.search(line) or not 3 <= len(words) <= 32:
        raise ValueError("English spoken line must contain 3-32 words and no CJK")
    expression = value["observable_expression"]
    required = {
        "facial_expression", "gaze", "speech_style", "prosody",
        "behavioral_cues",
    }
    if not isinstance(expression, dict) or set(expression) != required:
        raise ValueError("observable expression must contain the exact public fields")
    for key in required - {"behavioral_cues"}:
        text = str(expression[key]).strip()
        if not text or _CJK_PATTERN.search(text) or not _ENGLISH_WORD.search(text):
            raise ValueError(f"observable expression field {key} is not English")
        expression[key] = text
    cues = expression["behavioral_cues"]
    if not isinstance(cues, list) or len(cues) > 2:
        raise ValueError("behavioral_cues must be an English list with at most two items")
    clean_cues = []
    for cue in cues:
        text = str(cue).strip()
        if not text or _CJK_PATTERN.search(text) or not _ENGLISH_WORD.search(text):
            raise ValueError("behavioral cue is not English")
        if not _OBSERVABLE_CUE.search(text):
            raise ValueError("behavioral cue must describe a visible micro-action")
        clean_cues.append(text)
    expression["behavioral_cues"] = clean_cues
    return {"english_spoken_line": line, "observable_expression": expression}


def validate_compressed_line(value):
    if not isinstance(value, dict) or set(value) != {"english_spoken_line"}:
        raise ValueError("compressed line returned unexpected keys")
    line = str(value["english_spoken_line"]).strip()
    words = _ENGLISH_WORD.findall(line)
    if _CJK_PATTERN.search(line) or not 3 <= len(words) <= 32:
        raise ValueError("compressed English line must contain 3-32 words and no CJK")
    return {"english_spoken_line": line}


def compress_public_line(provider, payload, error):
    if not isinstance(error, StructuredOutputError):
        raise error
    if "English spoken line" not in str(error.last_error):
        raise error
    candidate = _parse_json_output(error.last_raw)
    if not isinstance(candidate, dict):
        raise error
    compressed = complete_json(
        provider,
        [{
            "role": "user",
            "content": render_prompt(
                VIDEO_PUBLIC_LINE_COMPRESSION_PROMPT_ID,
                candidate_line=candidate.get("english_spoken_line", ""),
            ),
        }],
        {"temperature": 0.1, "top_p": 0.9},
        validate_compressed_line,
        context="video public spoken-line compression",
        max_attempts=2,
    )
    candidate["english_spoken_line"] = compressed["english_spoken_line"]
    return validate_public_rendering(candidate)


def adapt_public_renderings(
    payloads, output, model_routes, workers, max_attempts=3
):
    cache_path = output / "public_rendering_adaptations.json"
    failures_path = output / "public_rendering_adaptation_failures.json"
    cache = (
        load(cache_path)
        if cache_path.exists()
        else {
            "format": "socialflux_video_public_rendering_adaptations_v1",
            "prompt_id": VIDEO_RENDERING_ADAPTATION_PROMPT_ID,
            "records": {},
        }
    )
    if cache.get("prompt_id") != VIDEO_RENDERING_ADAPTATION_PROMPT_ID:
        raise ValueError("video rendering adaptation cache prompt mismatch")
    records = cache.setdefault("records", {})
    routes = ModelRoutes.load(model_routes).require(["video_translation"])
    provider_config = routes.provider_config("video_translation")
    cache["model_routes_sha256"] = routes.sha256
    missing = [
        (key, payload) for key, payload in payloads.items() if key not in records
    ]

    def adapt_one(key, payload):
        seed = 41001 + int(key[:8], 16) % 2_000_000_000
        keywords = dict(
            validator=validate_public_rendering,
            context="video public rendering adaptation",
            max_attempts=max_attempts,
            retry_guidance=(
                "If the spoken line is too long, target 24-28 words and "
                "never exceed 32 words. Compress wording while preserving "
                "stance, commitments, boundaries, "
                "uncertainty, deadlines, and the most material public facts. "
                "Each behavioral cue must name a directly visible body, "
                "face, gaze, breath, posture, or hand micro-action."
            ),
        )
        last_transport_error = None
        request_count = 0
        for transport_attempt in range(3):
            provider = build_provider(provider_config)
            compression_used = False
            arguments = (
                provider,
                [{
                    "role": "user",
                    "content": render_prompt(
                        VIDEO_RENDERING_ADAPTATION_PROMPT_ID, payload
                    ),
                }],
                {"temperature": 0.1, "top_p": 0.9, "seed": seed},
            )
            try:
                try:
                    adapted = complete_json(*arguments, **keywords)
                except StructuredOutputError as exc:
                    adapted = compress_public_line(provider, payload, exc)
                    compression_used = True
            except (OSError, TimeoutError) as exc:
                request_count += provider_request_count(provider)
                last_transport_error = exc
                if transport_attempt < 2:
                    time.sleep(2 ** transport_attempt)
                    continue
                raise
            request_count += provider_request_count(provider)
            return key, {
                "source": payload,
                "adapted": adapted,
                "provider": public_provider_config(provider_config),
                "request_count": request_count,
                "transport_attempt_count": transport_attempt + 1,
                "line_compression_prompt_id": (
                    VIDEO_PUBLIC_LINE_COMPRESSION_PROMPT_ID
                    if compression_used else None
                ),
                "adapted_at_utc": now(),
            }
        raise last_transport_error

    failures = {}
    if missing:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(adapt_one, key, payload): key
                for key, payload in missing
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    key, record = future.result()
                except Exception as exc:
                    error = {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    }
                    last_error = getattr(exc, "last_error", None)
                    if last_error is not None:
                        error["validation_error"] = str(last_error)
                    last_raw = getattr(exc, "last_raw", None)
                    if last_raw is not None:
                        error["last_raw"] = last_raw
                    diagnostics = getattr(exc, "diagnostics", None)
                    if diagnostics:
                        error["diagnostics"] = diagnostics
                    failures[key] = {
                        "source": payloads[key],
                        "error": error,
                        "failed_at_utc": now(),
                    }
                    atomic(failures_path, {
                        "format": (
                            "socialflux_video_public_rendering_"
                            "adaptation_failures_v1"
                        ),
                        "failures": failures,
                    })
                    print(json.dumps({
                        "translation_error": key,
                        **failures[key]["error"],
                    }), flush=True)
                    continue
                records[key] = record
                atomic(cache_path, cache)
                print(json.dumps({
                    "translation_progress": len(records),
                    "translation_total": len(payloads),
                }), flush=True)
    atomic(cache_path, cache)
    if failures:
        raise RuntimeError(
            f"{len(failures)} public rendering adaptations failed; "
            f"successful records were retained in {cache_path}"
        )
    if failures_path.exists():
        previous = load(failures_path)
        active = previous.get("failures") or {}
        if active:
            history = previous.setdefault("resolved_failures", {})
            history.update(active)
        previous["failures"] = {}
        previous["active_failure_count"] = 0
        previous["resolved_failure_count"] = len(
            previous.get("resolved_failures") or {}
        )
        previous["resolved_at_utc"] = now()
        atomic(failures_path, previous)
    successful_model_request_count = sum(
        int(records[key].get("request_count", 0) or 0) for key in payloads
    )
    return {key: records[key]["adapted"] for key in payloads}, {
        "prompt_id": VIDEO_RENDERING_ADAPTATION_PROMPT_ID,
        "model_routes_sha256": routes.sha256,
        "unique_input_count": len(payloads),
        "new_adaptation_count": len(missing),
        "cache_hit_count": len(payloads) - len(missing),
        "logical_adaptation_request_count": len(payloads),
        "successful_model_request_count_recorded": (
            successful_model_request_count or None
        ),
        "cache_file": str(cache_path),
    }


def flatten_numeric(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            result.update(flatten_numeric(item, path))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result[prefix] = value
    return result


def importance(turn, turn_count):
    state = flatten_numeric(turn.get("numeric_state_delta", {}))
    dynamics = flatten_numeric(turn.get("numeric_dynamics_delta", {}))
    magnitude = sum(abs(value) for value in (*state.values(), *dynamics.values()))
    reasons = []
    score = float(magnitude)
    if magnitude:
        reasons.append("state_or_dynamics_change")
    if turn.get("trigger_events"):
        score += 4.0
        reasons.append("state_triggered_expression")
    claims = turn.get("response_consequential_claims") or []
    if claims:
        score += 3.0
        reasons.append("consequential_claim")
    ledger = turn.get("environment_response_ledger_events") or []
    consequential = {
        "commitment", "refusal", "boundary", "disclosure", "decision",
        "concession", "request",
    }
    if any(item.get("event_type") in consequential for item in ledger):
        score += 2.0
        reasons.append("socially_consequential_event")
    turn_id = int(str(turn.get("turn_id", "t0")).lstrip("t") or 0)
    if turn_id >= max(2, round(turn_count * 0.6)):
        score += 1.0
        reasons.append("history_bearing_late_checkpoint")
    return round(score, 4), reasons or ["coverage_checkpoint"]


def select_important_turns(trajectory, count, min_gap):
    turns = list(trajectory.get("turns", []))
    ranked = sorted(
        (
            (importance(turn, len(turns))[0], index, turn)
            for index, turn in enumerate(turns)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    selected = []
    for score, index, turn in ranked:
        if any(abs(index - old_index) < min_gap for _, old_index, _ in selected):
            continue
        selected.append((score, index, turn))
        if len(selected) == count:
            break
    if len(selected) < min(count, len(turns)):
        for score, index, turn in ranked:
            if any(index == old_index for _, old_index, _ in selected):
                continue
            selected.append((score, index, turn))
            if len(selected) == min(count, len(turns)):
                break
    return sorted(selected, key=lambda item: item[1])


def observable_behavior(scenario, turn):
    value = turn.get("response_observable_behavior")
    if isinstance(value, dict) and any(value.values()):
        return value
    value = turn.get("observable_expression")
    if isinstance(value, dict) and any(value.values()):
        return value
    return scenario.get("observable_expression", {}).get("default", {})



def stable_review_sample(records, count):
    best_by_scenario = {}
    for record in records:
        current = best_by_scenario.get(record["scenario_id"])
        if current is None or record["importance_score"] > current["importance_score"]:
            best_by_scenario[record["scenario_id"]] = record
    scenario_coverage = sorted(
        best_by_scenario.values(),
        key=lambda item: hashlib.sha256(
            item["request_id"].encode("utf-8")
        ).hexdigest(),
    )
    covered_ids = {item["request_id"] for item in scenario_coverage}
    remaining = sorted(
        (item for item in records if item["request_id"] not in covered_ids),
        key=lambda item: hashlib.sha256(
            item["request_id"].encode("utf-8")
        ).hexdigest(),
    )
    return (scenario_coverage + remaining)[:count]


def prepare(args):
    config = load(args.config)
    if config.get("format") != "socialflux_multimodal_generation_v1":
        raise ValueError("invalid multimodal generation config format")
    if config.get("prompt_id") != TALKING_HEAD_PROMPT_ID:
        raise ValueError("multimodal config prompt_id mismatch")
    offline = config["offline"]
    nodes_per_trajectory = int(
        args.nodes_per_trajectory or offline["important_nodes_per_trajectory"]
    )
    videos_per_node = int(args.videos_per_node or offline["videos_per_node"])
    min_turn_gap = int(args.min_turn_gap or offline["min_turn_gap"])
    duration = float(args.duration_seconds) if args.duration_seconds else None
    if not 1 <= nodes_per_trajectory <= 8:
        raise ValueError("important nodes per trajectory must be in 1..8")
    if not 1 <= videos_per_node <= 3:
        raise ValueError("videos per node must be in 1..3")
    if min_turn_gap < 1:
        raise ValueError("min turn gap must be positive")

    scenarios_list = load_actual_scenarios(args.scenario_root)
    for scenario in scenarios_list:
        validate_scenario(scenario)
    scenarios = {item["scenario_id"]: item for item in scenarios_list}
    continuity_references = (
        continuity_references_from_manifest(args.continuity_manifest)
        if args.continuity_manifest
        else {}
    )
    trajectories = load_records(args.rollout_root)
    for trajectory in trajectories:
        validate_trajectory(trajectory)
    if args.expected_count and len(trajectories) != args.expected_count:
        raise ValueError(
            f"expected {args.expected_count} trajectories, found {len(trajectories)}"
        )

    output = args.output or args.batch_root / "multimodal"
    gate2_output = args.gate2_output or (
        args.batch_root / "gate2" / "video_state_consistency.json"
    )
    requests_root = output / "requests"
    rendering_payloads = {}
    for trajectory in sorted(trajectories, key=lambda item: item["scenario_id"]):
        scenario = scenarios[trajectory["scenario_id"]]
        for _, _, turn in select_important_turns(
            trajectory, nodes_per_trajectory, min_turn_gap
        ):
            response = str(turn.get("environment_response", "")).strip()
            if not response:
                raise ValueError(
                    f"empty environment response at {trajectory['trajectory_id']} "
                    f"{turn.get('turn_id')}"
                )
            payload = rendering_payload(
                response, observable_behavior(scenario, turn)
            )
            rendering_payloads[rendering_key(payload)] = payload
    if not args.model_routes:
        raise ValueError("--model-routes is required for English video rendering")
    adapted_renderings, translation_provenance = adapt_public_renderings(
        rendering_payloads,
        output,
        args.model_routes,
        args.translation_workers,
        args.translation_max_attempts,
    )

    records = []
    for trajectory in sorted(trajectories, key=lambda item: item["scenario_id"]):
        scenario = scenarios[trajectory["scenario_id"]]
        selected = select_important_turns(
            trajectory, nodes_per_trajectory, min_turn_gap
        )
        for score, _, turn in selected:
            source_expression = observable_behavior(scenario, turn)
            source_response = str(turn.get("environment_response", "")).strip()
            payload = rendering_payload(source_response, source_expression)
            adapted = adapted_renderings[rendering_key(payload)]
            expression = adapted["observable_expression"]
            response = adapted["english_spoken_line"]
            _, reasons = importance(turn, len(trajectory["turns"]))
            for variant in range(1, videos_per_node + 1):
                request_id = (
                    f"{trajectory['scenario_id']}--{trajectory['trajectory_id']}--"
                    f"{turn['turn_id']}--v{variant}"
                )
                safe_name = hashlib.sha256(request_id.encode()).hexdigest()[:20]
                request_file = requests_root / f"{safe_name}.json"
                video_file = output / "assets" / f"{safe_name}.mp4"
                request = build_video_request(
                    scenario,
                    response,
                    expression,
                    duration_seconds=duration,
                    continuity_reference=continuity_references.get(
                        trajectory["scenario_id"]
                    ),
                    variant=variant,
                    expression_policy=config.get("expression_rendering"),
                )
                if (
                    args.require_continuity_reference
                    and request["reference_video_file"] is None
                ):
                    raise ValueError(
                        "missing scenario continuity reference: "
                        f"{trajectory['scenario_id']}"
                    )
                atomic(request_file, request)
                records.append({
                    "request_id": request_id,
                    "scenario_id": trajectory["scenario_id"],
                    "trajectory_id": trajectory["trajectory_id"],
                    "turn_id": turn["turn_id"],
                    "variant": variant,
                    "importance_score": score,
                    "importance_reasons": reasons,
                    "request_file": str(request_file.relative_to(args.batch_root)),
                    "video_file": str(video_file.relative_to(args.batch_root)),
                    "status": "request_ready",
                    "public_action": turn.get("policy_action", {}).get("text", ""),
                    "source_public_response": source_response,
                    "public_response": response,
                    "source_observable_expression": source_expression,
                    "observable_expression": expression,
                    "rendering_adaptation_key": rendering_key(payload),
                    "private_consistency_reference": {
                        "numeric_state_delta": turn.get("numeric_state_delta", {}),
                        "numeric_dynamics_delta": turn.get(
                            "numeric_dynamics_delta", {}
                        ),
                        "trigger_events": turn.get("trigger_events", []),
                    },
                })

    delivery = config.get("delivery") or {}
    manifest = {
        "format": "socialflux_multimodal_video_queue_v1",
        "created_at_utc": now(),
        "batch_root": str(args.batch_root.resolve()),
        "gate2_evidence_file": str(gate2_output),
        "mode": "offline_important_nodes",
        "prompt_id": TALKING_HEAD_PROMPT_ID,
        "network_requests_performed": 0,
        "video_network_requests_performed": 0,
        "translation_logical_adaptation_count": translation_provenance[
            "logical_adaptation_request_count"
        ],
        "translation_provider_requests_recorded": translation_provenance[
            "successful_model_request_count_recorded"
        ],
        "provider_status": "awaiting_video_api_configuration",
        "provider": {
            "resolution": delivery.get("resolution", "720p"),
            "ratio": delivery.get("ratio", "16:9"),
            "generate_audio": True,
            "watermark": False,
        },
        "continuity": {
            "manifest": (
                str(Path(args.continuity_manifest))
                if args.continuity_manifest
                else None
            ),
            "scenario_reference_count": len(continuity_references),
            "required": bool(args.require_continuity_reference),
        },
        "translation_provenance": translation_provenance,
        "trajectory_count": len(trajectories),
        "important_nodes_per_trajectory": nodes_per_trajectory,
        "videos_per_node": videos_per_node,
        "request_count": len(records),
        "requests": records,
    }
    atomic(output / "manifest.json", manifest)

    review_count = int(config["gate2"]["video_review_sample_count"])
    review_records = stable_review_sample(records, review_count)
    gate2 = {
        "format": "socialflux_environment_video_state_consistency_v1",
        "created_at_utc": now(),
        "record": {
            "human_attestation": False,
            "reviewers": [],
            "reviewed_at_utc": "",
            "review_status": "pending_video_api_and_review",
            "llm_review_status": "pending",
            "matched_node_count": len(review_records),
            "generated_video_count": 0,
            "request_safety_passed": all(
                all(value is False for value in load(
                    args.batch_root / item["request_file"]
                )["safety_check"].values())
                for item in review_records
            ),
            "machine_screen_passed": False,
            "passed": False,
        },
        "review_items": [
            {
                **item,
                "ratings": {
                    "state_expression_alignment": None,
                    "persona_consistency": None,
                    "temporal_continuity": None,
                    "lip_sync_and_speech_naturalness": None,
                    "no_private_state_leakage": None,
                    "overall": None,
                },
                "llm_review": "pending",
                "human_review": "pending",
            }
            for item in review_records
        ],
    }
    atomic(gate2_output, gate2)
    print(json.dumps({
        "trajectory_count": len(trajectories),
        "request_count": len(records),
        "gate2_review_items": len(review_records),
        "network_requests_performed": 0,
        "output": str(output),
        "gate2_output": str(gate2_output),
    }, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gate2-output", type=Path)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--nodes-per-trajectory", type=int)
    parser.add_argument("--videos-per-node", type=int)
    parser.add_argument("--min-turn-gap", type=int)
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--model-routes", type=Path)
    parser.add_argument("--translation-workers", type=int, default=2)
    parser.add_argument("--translation-max-attempts", type=int, default=3)
    parser.add_argument("--continuity-manifest", type=Path)
    parser.add_argument("--require-continuity-reference", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.translation_workers <= 8:
        parser.error("translation-workers must be in 1..8")
    if not 1 <= args.translation_max_attempts <= 3:
        parser.error("translation-max-attempts must be in 1..3")
    prepare(args)


if __name__ == "__main__":
    main()
