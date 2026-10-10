#!/usr/bin/env python3
"""Frozen 10-case state-only check plus two predeclared boundary retests."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.calibration import DeterministicStateCalibrator
from environment.independent_appraisal import ModelStateAppraiser
from environment.delta_mapper import flatten_state
from environment.public_situation import render_public_background
from prompts.loader import prompt_manifest
from providers.factory import build_provider, public_provider_config
from rollout.configuration import load_rollout_config
from scripts.run_state_appraiser_backbone_probe import build_cases, find_turn
from scripts.run_state_judgment_primary_fixed_validation import common_kwargs

BASE = ROOT / "data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary"
CONFIG = ROOT / "configs/gpt50_experiment/rollout.state_independent_per_variable_v3_state_judgment_primary_candidate.json"
OUTPUT = BASE / "context_samples_v724_corrected"
PROMPT = "environment_state_appraisal_v5_immediate_context"
NEW = {"ordinary_new_evidence", "decisive_new_evidence"}


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


class Captured(Exception):
    pass


class Capture:
    def complete(self, messages, **generation):
        self.request = {"messages": deepcopy(messages), "generation": generation}
        raise Captured()


def prepare_case(case, env):
    scenario = load(ROOT / case["scenario"])
    source = load(ROOT / case["source"])
    turn = deepcopy(find_turn(source, case["turn_id"]))
    if case["action_override"] is not None:
        turn["policy_action"] = {"text": case["action_override"]}
    kwargs = common_kwargs(turn, source["turns"])
    kwargs.pop("current_event_id")
    capture = Capture()
    appraiser = ModelStateAppraiser(scenario, capture, env["state_appraisal_sampling"], prompt_id=PROMPT)
    try:
        appraiser.appraise(**kwargs)
    except Captured:
        pass
    request = capture.request
    payload = json.loads(request["messages"][1]["content"].split("## Input\n", 1)[1])
    context = payload["appraisal_context"]
    assert context["current_turn"]["action_text"] == turn["policy_action"]["text"].strip()
    assert context["current_turn"]["turn_id"] == case["turn_id"]
    assert context["historical_messages"] == turn["observation"]["history"]
    assert payload["memory"]["duplicate_evidence_matches"] == context["duplicate_evidence_matches"]
    assert "prior_numeric_update" not in json.dumps(context)
    assert all("two independent" not in v["update_rule"] for v in payload["state_semantics"]["variables"].values())
    assert "update_policy" in payload["state_semantics"]
    if case["case_id"] == "trust_gpt003_exact_restatement_control":
        assert [m["historical_turn_id"] for m in context["duplicate_evidence_matches"]] == ["t2"]
        assert "今晚这条指令" in context["latest_unanswered_question"]
    for fragment in ("later confirms", "later records will show", "notes clarifies the wish"):
        assert fragment not in payload["background"]
    return {"case": case, "scenario": scenario, "kwargs": kwargs,
            "request": request, "payload": payload}


class LoggedProvider:
    def __init__(self, provider, directory, expected):
        self.provider, self.directory, self.expected = provider, directory, expected
        self.requests = []

    def __getattr__(self, key):
        return getattr(self.provider, key)

    def complete(self, messages, **generation):
        if not self.requests:
            assert {"messages": messages, "generation": generation} == self.expected
        record = {"messages": deepcopy(messages), "generation": generation,
                  "started_at": datetime.now(timezone.utc).isoformat()}
        self.requests.append(record)
        save(self.directory / "requests.json", self.requests)
        try:
            raw = self.provider.complete(messages, **generation)
            record["raw_output"] = raw
            return raw
        except Exception as exc:
            record["error"] = {"type": type(exc).__name__, "message": str(exc),
                               "raw_output": getattr(exc, "raw_output", None)}
            raise
        finally:
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            record["provider_audit_records"] = deepcopy(getattr(self.provider, "audit_records", []))
            save(self.directory / "requests.json", self.requests)


def run_one(index, prepared, env, provider_config):
    directory = OUTPUT / f"{index:02d}_{prepared['case']['case_id']}"
    provider = LoggedProvider(build_provider(deepcopy(provider_config)), directory, prepared["request"])
    start = time.monotonic()
    result = {"case": prepared["case"], "checkpoint_mode": "full_observed_history_empty_numeric_accumulator"}
    try:
        state = ModelStateAppraiser(
            prepared["scenario"], provider, env["state_appraisal_sampling"], prompt_id=PROMPT
        ).appraise(**deepcopy(prepared["kwargs"]))
        transition = DeterministicStateCalibrator(
            prepared["scenario"], profile=env["state_calibration_profile"]
        ).calibrate(state["appraisal"], prepared["kwargs"]["previous_state"],
                    prepared["kwargs"]["previous_dynamics"],
                    current_event_id=prepared["case"]["turn_id"])
        judgment = next(x for x in state["state_judgments"] if x["variable"] == prepared["case"]["target"])
        delta = flatten_state(transition["state_delta"])[prepared["case"]["target"]]
        expected = prepared["case"]["expected_judgment"]
        observed_new, expected_new = judgment["judgment"] in NEW, expected in NEW
        audits = provider.audit_records
        result.update({
            "status": "completed", "target_judgment": judgment, "target_delta": delta,
            "recognition_correct": observed_new == expected_new,
            "strength_correct": judgment["judgment"] == expected,
            "false_positive": observed_new and not expected_new,
            "false_negative": expected_new and not observed_new,
            "direction_correct": (not expected_new or judgment["direction"] == prepared["case"]["expected_direction"]),
            "call_complete": bool(audits) and all(x.get("complete") is True for x in audits),
            "state_appraisal": state, "transition": transition,
        })
    except Exception as exc:
        result.update({"status": "call_failure", "error_type": type(exc).__name__,
                       "error": str(exc), "raw_output": getattr(exc, "raw_output", None)})
    result["provider_metrics"] = deepcopy(getattr(provider, "metrics", {}))
    result["elapsed_seconds"] = time.monotonic() - start
    save(directory / "result.json", result)
    print(json.dumps({k: result.get(k) for k in
                      ("status", "target_delta", "recognition_correct", "false_positive", "error")},
                     ensure_ascii=False), prepared["case"]["case_id"], flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    config = load_rollout_config(CONFIG)
    env = config["environment"]
    assert env["state_appraisal_prompt_id"] == PROMPT
    positives, negatives = BASE / "human_confirmed_fixed_set.json", BASE / "negative_control_candidates.json"
    cases = build_cases(positives, negatives)
    labels = {c["case_id"]: c["adjudicated_label"] for c in load(positives)["cases"]}
    labels.update({c["case_id"]: c["proposed_human_label"] for c in load(negatives)["controls"]})
    for case in cases:
        case["expected_direction"] = labels[case["case_id"]]["direction"]
        case["label_status"] = "human_confirmed"
    # Declared before seeing outputs: original costly disclosure and exact repeat.
    schedule = cases + [deepcopy(c) for c in cases if c["case_id"] in
                        {"trust_gpt003__positive", "trust_gpt003_exact_restatement_control"}]
    prepared = [prepare_case(case, env) for case in schedule]
    provider = deepcopy(env.get("state_appraisal_provider", env["provider"]))
    provider["timeout"] = 300
    provider["max_candidates_per_request"] = 1
    for candidate in provider.get("candidates", []):
        candidate["timeout"] = 300
        candidate["max_transport_attempts"] = 1
    inputs = [{"case": item["case"], "request": item["request"], "payload": item["payload"]} for item in prepared]
    digest = hashlib.sha256(json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    prereg = {"status": "prepared", "schedule": [x["case_id"] for x in schedule],
              "fixed_case_count": 10, "predeclared_retests": 2, "model": provider["model"],
              "provider": public_provider_config(provider), "prompt": PROMPT,
              "prompt_sha256": prompt_manifest()["prompts"][PROMPT]["sha256"],
              "inputs_sha256": digest, "transport_override": "300s; one route attempt; schema retries retained and logged",
              "preflight_passed": True, "model_calls": 0, "full_scale_authorized": False}
    frozen = OUTPUT / "preregistration.json"
    if frozen.exists():
        assert load(frozen)["inputs_sha256"] == digest, "frozen inputs changed"
    else:
        save(frozen, prereg)
        save(OUTPUT / "prepared_requests.json", inputs)
    print("preflight: 12 actual request payloads checked; repeat matches t2; all labels frozen", flush=True)
    if not args.run:
        return
    target = OUTPUT / "results.json"
    if target.exists():
        raise FileExistsError("refusing a repeated run")
    report = {"status": "running", "rows": {}, "full_scale_authorized": False}
    save(target, report)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run_one, i, item, env, provider): i for i, item in enumerate(prepared)}
        for future in as_completed(futures):
            report["rows"][str(futures[future])] = future.result()
            save(target, report)
    report["status"] = "completed"
    report["summary"] = {}
    for name, keys in (("fixed", range(10)), ("boundary_retests", range(10, 12))):
        rows = [report["rows"][str(i)] for i in keys]
        completed = [r for r in rows if r["status"] == "completed"]
        report["summary"][name] = {
            "scheduled": len(rows), "completed": len(completed),
            **{key: sum(bool(r.get(key)) for r in completed) for key in
               ("recognition_correct", "strength_correct", "direction_correct",
                "false_positive", "false_negative", "call_complete")},
        }
    save(target, report)
    lines = ["State sample results (state-only; full historical dialogue; not full-rollout validation)", ""]
    for i, item in enumerate(prepared):
        row = report["rows"][str(i)]
        context = item["payload"]["appraisal_context"]
        lines.extend([f"{i+1}. {row['case']['case_id']}",
                      "Latest environment utterance: " + str((context["latest_environment_utterance"] or {}).get("text", "")),
                      "Current action: " + context["current_turn"]["action_text"],
                      "Expected: " + row["case"]["expected_judgment"],
                      "Observed: " + json.dumps(row.get("target_judgment", row.get("error")), ensure_ascii=False),
                      "Delta: " + str(row.get("target_delta")), ""])
    (OUTPUT / "review.txt").write_text("\n".join(lines))
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
