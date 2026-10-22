#!/usr/bin/env python3
"""Build one visualizable packet for every human review role."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.delta_mapper import flatten_state
from evaluation.instance_quality import blind_instance_packet
from evaluation.quality_gates import (
    TASK_REVIEW_RATINGS,
    deterministic_task_review_sample,
)
from evaluation.rollout_gate import content_sha256
from scripts.audit_formal_rollout_pool import load_records
from scenario_design.catalog import discover_scenario_paths


ROOT = Path(__file__).resolve().parents[1]


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_instances(root):
    records = []
    for path in sorted(root.glob("*/offline/instances.jsonl")):
        records.extend(
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return records


def load_actual_scenarios(root):
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in discover_scenario_paths(Path(root))
    ]


def _stable_rank(value):
    return hashlib.sha256(f"socialflux-human-review-v1:{value}".encode("utf-8")).hexdigest()


def _state_value(state, state_id):
    return flatten_state(state).get(state_id)


def _direction(before, after):
    if before is None or after is None:
        return "cannot_determine"
    return "increase" if after > before else "decrease" if after < before else "similar"


def machine_task_proposal(instance, trajectories, interventions):
    """Derive an auditable machine proposal; never write formal ground truth."""
    metadata = instance.get("metadata", {})
    targets = instance.get("target_spec", {}).get("target_state_ids", [])
    task_type = instance.get("task_type")
    if task_type == "T1_state_tracking":
        source = trajectories.get(metadata.get("source_trajectory_id"), {})
        depth = len(instance.get("input", {}).get("history", []))
        turns = source.get("turns", [])
        if not turns or depth < 1 or depth > len(turns):
            return {"status": "unavailable", "reason": "source checkpoint missing"}
        state = turns[depth - 1].get(
            "state_after_public_events", turns[depth - 1].get("state_after", {})
        )
        return {
            "status": "machine_proposal_not_ground_truth",
            "labels": {key: _state_value(state, key) for key in targets},
            "evidence": [turns[depth - 1].get("turn_id")],
        }
    if task_type == "T2_history_sensitive_merge":
        source_ids = metadata.get("source_trajectory_ids", [])
        depth = len(instance.get("input", {}).get("history_a", []))
        if len(source_ids) != 2 or any(item not in trajectories for item in source_ids):
            return {"status": "unavailable", "reason": "paired source checkpoints missing"}
        left, right = (trajectories[item] for item in source_ids)
        if depth < 1 or depth > min(len(left.get("turns", [])), len(right.get("turns", []))):
            return {"status": "unavailable", "reason": "paired checkpoint depth missing"}
        left_state = left["turns"][depth - 1].get(
            "state_after_public_events", left["turns"][depth - 1].get("state_after", {})
        )
        right_state = right["turns"][depth - 1].get(
            "state_after_public_events", right["turns"][depth - 1].get("state_after", {})
        )
        labels = {}
        for key in targets:
            a, b = _state_value(left_state, key), _state_value(right_state, key)
            labels[key] = (
                "cannot_determine" if a is None or b is None else
                "higher_in_a" if a > b else "higher_in_b" if b > a else "similar"
            )
        return {
            "status": "machine_proposal_not_ground_truth",
            "labels": labels,
            "evidence": [left["turns"][depth - 1].get("turn_id"), right["turns"][depth - 1].get("turn_id")],
        }
    if task_type == "T3_counterfactual_choice_effect":
        key = (metadata.get("source_trajectory_id"), metadata.get("checkpoint_turn_id"))
        branches = interventions.get(key, [])
        by_action = {item.get("candidate_action", {}).get("text"): item for item in branches}
        labels = []
        missing = []
        for action in instance.get("input", {}).get("candidate_actions", []):
            branch = by_action.get(action.get("text"))
            if not branch:
                missing.append(action.get("text"))
                continue
            option = {"action": action.get("text"), "immediate": {}, "delayed": {}}
            for target in targets:
                before = _state_value(branch.get("state_before", {}), target)
                option["immediate"][target] = _direction(
                    before, _state_value(branch.get("state_after_immediate", {}), target)
                )
                option["delayed"][target] = _direction(
                    before, _state_value(branch.get("state_after_delayed", {}), target)
                )
            labels.append(option)
        return {
            "status": "machine_proposal_not_ground_truth" if not missing else "partial",
            "labels": labels,
            "missing_actions": missing,
            "evidence": [metadata.get("checkpoint_turn_id")],
        }
    return {"status": "unavailable", "reason": "unknown task type"}


def blank_review(task_type):
    return {
        "reviewer": "",
        "reviewed_at_utc": "",
        "review_status": "pending",
        "human_attestation": False,
        "ratings": {key: None for key in sorted(TASK_REVIEW_RATINGS[task_type])},
        "notes": "",
    }


def gate4_packet(instances, proposals, plan):
    config = plan["gate4"]
    fraction = config["sample_fraction_per_task_type"]
    minimum = config["minimum_sample_per_task_type"]
    sampled = deterministic_task_review_sample(instances, fraction, minimum)
    records = []
    for instance in sampled:
        records.append({
            "instance_id": instance["instance_id"],
            "scenario_id": instance.get("story_id"),
            "task_type": instance["task_type"],
            "instance_sha256": content_sha256(instance),
            "blind_packet": blind_instance_packet(instance),
            "machine_proposal": proposals[instance["instance_id"]],
            "reviews": {
                "reviewer_a": blank_review(instance["task_type"]),
                "reviewer_b": blank_review(instance["task_type"]),
            },
            "adjudication": blank_review(instance["task_type"]),
        })
    counts = Counter(item["task_type"] for item in records)
    return {
        "format": "socialflux_gate4_double_audit_v2",
        "sampling": {
            "strategy": "sha256_ranked_stratified_by_task_type_v1",
            "fraction_per_task_type": fraction,
            "minimum_per_task_type": minimum,
            "same_sample_for_both_reviewers": True,
            "population_count": len(instances),
            "sample_count": len(records),
            "sample_counts": dict(counts),
        },
        "instructions": {
            "reviewers": "Reviewer A and B independently inspect the same blind packet, then compare with the collapsed machine proposal.",
            "agreement": "Both approve: accept sampled item. Both reject: send item/family back for repair.",
            "disagreement": "Only A/B disagreement is routed to a distinct third named adjudicator.",
            "boundary": "machine_proposal is an audit aid, not formal human ground truth",
        },
        "records": records,
    }


def e1_packet(trajectories, scenarios):
    by_scenario = defaultdict(list)
    for trajectory in trajectories:
        for turn in trajectory.get("turns", []):
            by_scenario[trajectory["scenario_id"]].append((trajectory, turn))
    items = []
    for scenario_id, candidates in sorted(by_scenario.items()):
        for trajectory, turn in sorted(
            candidates,
            key=lambda pair: _stable_rank(f"E1:{scenario_id}:{pair[0]['trajectory_id']}:{pair[1]['turn_id']}")
        )[:2]:
            scenario = scenarios[scenario_id]
            collapsed = {}
            for key, value in flatten_state(turn.get("numeric_state_delta", {})).items():
                collapsed[key] = "increase" if value > 0 else "decrease" if value < 0 else "similar"
            items.append({
                "review_id": f"E1:{scenario_id}:{trajectory['trajectory_id']}:{turn['turn_id']}",
                "scenario_id": scenario_id,
                "source_trajectory_id": trajectory["trajectory_id"],
                "source_status": trajectory.get("gate2_audit_input", {}).get(
                    "source_status", "accepted_or_unspecified"
                ),
                "turn_id": turn["turn_id"],
                "persona": scenario["environment_agent"].get("persona", {}),
                "relevant_history": turn.get("memory_view", {}),
                "latest_action": turn.get("policy_action", {}).get("text", ""),
                "human_directions": {key: None for key in collapsed},
                "machine_directions_after_vote": collapsed,
                "review_status": "pending",
            })
    return items


def e2_packet(trajectories):
    grouped = defaultdict(list)
    for trajectory in trajectories:
        grouped[trajectory["scenario_id"]].append(trajectory)
    selected = [
        sorted(items, key=lambda item: _stable_rank(f"E2:{item['trajectory_id']}"))[0]
        for _, items in sorted(grouped.items())
    ]
    return [{
        "review_id": f"E2:{item['scenario_id']}:{item['trajectory_id']}",
        "scenario_id": item["scenario_id"],
        "trajectory_id": item["trajectory_id"],
        "source_status": item.get("gate2_audit_input", {}).get(
            "source_status", "accepted_or_unspecified"
        ),
        "turn_count": len(item.get("turns", [])),
        "policy_id": item.get("policy_id"),
        "turns": [{
            "turn_id": turn.get("turn_id"),
            "action": turn.get("policy_action", {}).get("text", ""),
            "response": turn.get("environment_response", ""),
            "state_delta": turn.get("numeric_state_delta", {}),
        } for turn in item.get("turns", [])],
        "scores": {
            "persona_consistency": None,
            "history_sensitivity": None,
            "state_continuity": None,
            "response_state_consistency": None,
            "overall": None,
        },
        "review_status": "pending",
    } for item in selected]


def pending_e1_e2(output_root, e1, e2):
    common = {"human_attestation": False, "reviewers": [], "reviewed_at_utc": "", "review_status": "pending_human"}
    direction_counts = Counter(
        direction
        for item in e1
        for direction in item.get("machine_directions_after_vote", {}).values()
    )
    family_counts = defaultdict(Counter)
    for item in e1:
        for state_id, direction in item.get(
            "machine_directions_after_vote", {}
        ).items():
            family_counts[state_id.split(".", 1)[0]][direction] += 1
    source_status_counts = Counter(
        item.get("source_status", "accepted_or_unspecified") for item in e1
    )
    e2_source_status_counts = Counter(
        item.get("source_status", "accepted_or_unspecified") for item in e2
    )
    payloads = {
        "state_transition_agreement.json": {
            "format": "socialflux_state_transition_agreement_v1",
            "record": {
                **common,
                "annotator_count": 0,
                "transition_count": len(e1),
                "agreement": None,
                "machine_direction_counts": dict(direction_counts),
                "machine_direction_counts_by_state_family": {
                    key: dict(value)
                    for key, value in sorted(family_counts.items())
                },
                "machine_unchanged_fraction": round(
                    direction_counts.get("similar", 0)
                    / sum(direction_counts.values()), 4
                ) if direction_counts else None,
                "source_status_counts": dict(source_status_counts),
                "sampling_policy": "stable_hash_over_transitions; independent_of_direction",
            },
            "review_items": e1,
        },
        "trajectory_plausibility.json": {
            "format": "socialflux_trajectory_plausibility_v1",
            "record": {**common, "annotator_count": 0, "trajectory_count": len(e2), "source_status_counts": dict(e2_source_status_counts), "turn_count_distribution": dict(Counter(item.get("turn_count", 0) for item in e2)), "sampling_policy": "stable_hash_over_trajectories; independent_of_quality_outcome", "scores": {"persona_consistency": None, "history_sensitivity": None, "state_continuity": None, "response_state_consistency": None, "overall": None}},
            "review_items": e2,
        },
    }
    for filename, payload in payloads.items():
        target = output_root / filename
        existing = read_json(target, {}) or {}
        if existing.get("record", existing).get("human_attestation") is not True:
            write_json(target, payload)
    return payloads


def model_stack(config):
    environment = config["environment"]
    policies = []
    for item in config.get("policies", []):
        policies.append({
            "role": "evaluated_agent_policy",
            "policy_id": item.get("policy_id"),
            "model_family": item.get("model_family"),
            "model": item.get("provider", {}).get("model"),
            "runs": item.get("runs", 1),
        })
    return {
        "environment": {
            "role": "appraisal_state_update_and_environment_response",
            "model": environment.get("provider", {}).get("model"),
            "sampling": environment.get("sampling", {}),
            "note": "The provider performs separate appraisal and visible-response calls; deterministic calibration and numeric state update occur between them.",
        },
        "evaluated_agent_policies": policies,
        "warning": "Changing the environment response model changes the Gate 2 condition and requires a new matched validity run before formal rollout.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-root", type=Path, default=ROOT / "configs" / "scenarios")
    parser.add_argument("--rollout-root", type=Path, default=ROOT / "build" / "rollout_20turn_3candidate")
    parser.add_argument("--screening-report", type=Path, default=ROOT / "build" / "rollout_20turn_3candidate" / "screening_report.json")
    parser.add_argument("--pipeline-root", type=Path, default=ROOT / "build" / "pipeline_20turn_selected")
    parser.add_argument("--environment-root", type=Path, default=ROOT / "data" / "formal" / "environment")
    parser.add_argument(
        "--stabilization-regression",
        type=Path,
        default=ROOT / "data" / "formal" / "environment" / "stabilization_rollout_regression.json",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "human_review_workspace.json")
    parser.add_argument("--task-review-output", type=Path, default=ROOT / "reviews" / "task_review_sample_template.json")
    parser.add_argument("--machine-proposals-output", type=Path, default=ROOT / "build" / "machine_task_proposals.json")
    parser.add_argument(
        "--refresh-e1-e2", action="store_true",
        help="Replace E1/E2 packets from active rollouts; omit to preserve existing evidence.",
    )
    args = parser.parse_args()
    plan = read_json(ROOT / "configs" / "human_review_plan.json")
    scenarios_list = load_actual_scenarios(args.scenario_root)
    scenarios = {item["scenario_id"]: item for item in scenarios_list}
    trajectories_list = load_records(args.rollout_root)
    trajectories = {item["trajectory_id"]: item for item in trajectories_list}
    instances = load_instances(args.pipeline_root)
    interventions_by_key = defaultdict(list)
    for path in sorted(args.pipeline_root.glob("*/validation/local_action_interventions.json")):
        for item in read_json(path, []) or []:
            interventions_by_key[(item.get("source_trajectory_id"), item.get("checkpoint_turn_id"))].append(item)
    if args.refresh_e1_e2:
        if not trajectories_list:
            raise SystemExit("cannot refresh E1/E2: active rollout root has no completed trajectories")
        e1 = e1_packet(trajectories_list, scenarios)
        e2 = e2_packet(trajectories_list)
        pending_e1_e2(args.environment_root, e1, e2)
    proposals = {
        instance["instance_id"]: machine_task_proposal(
            instance, trajectories, interventions_by_key
        )
        for instance in instances
    }
    proposal_payload = {
        "format": "socialflux_machine_task_proposals_v1",
        "warning": "These labels are machine proposals derived from frozen private state/branches, not human ground truth.",
        "population_count": len(instances),
        "records": [
            {
                "instance_id": instance["instance_id"],
                "scenario_id": instance.get("story_id"),
                "task_type": instance["task_type"],
                "instance_sha256": content_sha256(instance),
                "proposal": proposals[instance["instance_id"]],
            }
            for instance in instances
        ],
    }
    write_json(args.machine_proposals_output, proposal_payload)
    task_packet = gate4_packet(instances, proposals, plan)
    write_json(args.task_review_output, task_packet)
    gate2 = {}
    for experiment_id, filename in (
        ("E1", "state_transition_agreement.json"),
        ("E2", "trajectory_plausibility.json"),
        ("E3", "history_intervention.json"),
        ("E4", "paraphrase_robustness.json"),
        ("E5", "local_counterfactual.json"),
        ("E6", "backbone_sensitivity.json"),
        ("E7", "persona_intervention.json"),
        ("E8", "video_state_consistency.json"),
        ("E9", "timescale_validity.json"),
    ):
        gate2[experiment_id] = read_json(args.environment_root / filename, {
            "record": {"review_status": "not_generated", "human_attestation": False},
            "records": [],
        })
    formal_config = read_json(ROOT / "configs" / "rollout_20turn_3candidate_development.local.json", {}) or {}
    screening = read_json(args.screening_report, {}) or {}
    active_gate3_records = [
        item for item in screening.get("records", [])
        if item.get("source_stage") == "active_candidate"
    ]
    secondary_gate3_count = math.ceil(
        len(active_gate3_records) * plan["gate3"]["secondary_audit_fraction"]
    )
    secondary_gate3_records = sorted(
        active_gate3_records,
        key=lambda item: _stable_rank(f"GATE3-AUDIT:{item.get('trajectory_id')}")
    )[:secondary_gate3_count]
    media = read_json(ROOT / "media" / "talking_head" / "manifest.json", {}) or {}
    scenario_reviews = read_json(ROOT / "reviews" / "scenario_review_template.json", {}) or {}
    workspace = {
        "format": "socialflux_human_review_workspace_v1",
        "staffing_plan": plan,
        "model_stack": model_stack(formal_config),
        "counts": {
            "scenarios": len(scenarios),
            "development_trajectories": len(trajectories),
            "task_population": len(instances),
            "machine_proposals": sum(
                item.get("status") == "machine_proposal_not_ground_truth"
                for item in proposals.values()
            ),
            "gate4_sample": task_packet["sampling"]["sample_count"],
            "videos": len(media.get("assets", [])),
        },
        "gate1": {
            "instructions": "One reviewer checks every scenario and freezes its initial state; the runtime dynamics seed is machine-validated and not separately human-frozen. Signed hash-bound approval remains required.",
            "records": scenario_reviews.get("records", []),
        },
        "gate2": gate2,
        "environment_stabilization_regression": read_json(
            args.stabilization_regression,
            {
                "record": {
                    "trajectory_count": 0,
                    "review_status": "not_generated",
                    "human_attestation": False,
                },
                "records": [],
            },
        ),
        "gate3": {
            "instructions": "One primary reviewer covers active candidates; a second reviewer audits the deterministic 20%. Archived rejected attempts remain failure-analysis evidence, not primary workload.",
            "summary": screening.get("summary", {}),
            "primary_records": active_gate3_records,
            "primary_count": len(active_gate3_records),
            "secondary_audit_fraction": plan["gate3"]["secondary_audit_fraction"],
            "secondary_audit_records": secondary_gate3_records,
            "secondary_audit_count": len(secondary_gate3_records),
            "archive_failure_records": [
                item for item in screening.get("records", [])
                if item.get("source_stage") != "active_candidate"
            ],
        },
        "gate4": task_packet,
        "video": {
            "instructions": "One reviewer checks every released talking-head asset for identity, lip sync, expression/state fit and realism.",
            "quality_gate": read_json(ROOT / "media" / "talking_head" / "quality_gate_report.json", {}) or {},
            "assets": media.get("assets", []),
        },
        "warning": (
            "All unsigned reviewer fields remain pending. Gate 3/4 expose only the new "
            "20-turn pool and its selected-task pipeline; legacy 6-turn/180-task data are "
            "excluded. Machine proposals and automatic screens are not human attestations."
        ),
    }
    write_json(args.output, workspace)
    print(json.dumps({"output": str(args.output), **workspace["counts"], "gate4_by_task": task_packet["sampling"]["sample_counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
