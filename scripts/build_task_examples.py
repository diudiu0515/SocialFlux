#!/usr/bin/env python3
"""Build three reviewable SocialFlux task examples and optional LLM answers.

The examples are deliberately kept separate from formal ground truth.  They are
small, leakage-safe teaching/review artifacts that exercise the same T1/T2/T3
contracts as the benchmark builders.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.leakage import assert_no_leaks
from offline.rollout_builders import build_t1_checkpoints, build_t2_pair, build_t3_candidates
from prompts.loader import render_prompt
from providers.factory import build_provider
from providers.model_routes import ModelRoutes
from providers.structured import complete_json
from tasks.T1.t1_probability_utils import INTENSITY_LABELS, validate_probabilities as validate_t1_probs
from tasks.T2.t2_probability_utils import validate_probabilities as validate_t2_probs
from tasks.T3.t3_probability_utils import validate_probabilities as validate_t3_probs


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "task_examples_v1"
MANIFEST = OUTPUT / "examples.json"
MODEL_ROUTES = ROOT / "configs" / "model_routes.frontier_api.json"

T1_SOURCE = ROOT / "build/scale150_v1/rollouts_v2/shard2/scenario_006/d776a7e9965e4745a0153bbe90168868.json"
T2_SOURCE_A = ROOT / "configs/scenarios/scenario_018/rollouts/1cf7b1a2cddd4ebe90039b1711e0bab2.json"
T2_SOURCE_B = ROOT / "configs/scenarios/scenario_018/rollouts/d0b2ccea13804acc88f9b9eab3017887.json"
SCENARIO_006 = ROOT / "configs/scale150_v1/scenarios/scenario_006/scenario_006.json"
SCENARIO_018 = ROOT / "configs/scenarios/scenario_018/scenario_018.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact_history(trajectory, through_index):
    """Preserve every public utterance/event without duplicating large ledgers."""
    result = []
    for turn in trajectory["turns"][: through_index + 1]:
        record = {
            "turn_id": turn["turn_id"],
            "evaluated_agent": turn["policy_action"]["text"],
            "environment_character": turn["environment_response"],
            "public_events_after": deepcopy(
                (turn.get("segment_transition_after") or {}).get("public_events", [])
            ),
        }
        result.append(record)
    return result


def compact_role_context(turn):
    observation = turn["observation"]
    return {
        "scenario_id": observation["scenario_id"],
        "background": observation.get("background", ""),
        "evaluated_agent": deepcopy(observation.get("role", {})),
        "target_character": deepcopy(observation.get("target_character", {})),
    }


def media_descriptor(asset_id, path, expression, *, shown_to_model=True):
    return {
        "asset_id": asset_id,
        "media_type": "video",
        "url": (f"/task-media/{Path(path).name}"
                if path.startswith("media/task_examples/")
                else f"/media/{asset_id}"),
        "path": path,
        "observable_expression": expression,
        "shown_to_model": shown_to_model,
        "contains_state_label": False,
    }


def build_t1():
    trajectory = load(T1_SOURCE)
    scenario = load(SCENARIO_006)
    turn_index = 9  # completed t10: evidence boundary and publication wording are settled
    original = build_t1_checkpoints(
        trajectory, scenario["target_state_ids"]
    )[turn_index]
    context = compact_role_context(trajectory["turns"][0])
    history = compact_history(trajectory, turn_index)
    media = media_descriptor(
        "TASK_EXAMPLE_T1--editor_evidence_acceptance",
        "media/task_examples/t1_editor_evidence_acceptance.mp4",
        {
            "facial_expression": "严肃感保留，眉间略微放松",
            "gaze": "先核对材料，再稳定看向记者",
            "head_motion": "说到‘现有证据’时轻微点头",
            "response_timing": "短暂停顿核对后作出决定",
            "overall_behavior": "谨慎接受可证实的报道边界",
        },
    )
    current = {
        "turn_id": "t10",
        "current_response": trajectory["turns"][turn_index]["environment_response"],
        "observable_cues": [],
        "observable_expression": media["observable_expression"],
        "media": [],
    }
    original["instance_id"] = "TASK_EXAMPLE_T1_001"
    original["input"] = {
        **context,
        "history": history,
        "current_checkpoint": current,
    }
    original["target_spec"].update({
        "intensity_labels": list(INTENSITY_LABELS),
        "change_labels": ["increase", "similar", "decrease", "cannot_determine"],
    })
    original["metadata"].update({
        "source_artifact": str(T1_SOURCE.relative_to(ROOT)),
        "source_sha256": digest(T1_SOURCE),
        "source_gate_evidence": "Scale300 aggregate: machine precheck + model semantic approve; human pending",
        "example_checkpoint_reason": "t10 resolves a fact boundary after a public legal-review event",
        "codex_full_text_review": "usable_example_with_source_limitations",
        "source_limitations": [
            "the source dialogue contains some procedural repetition",
            "this example is for task/UI validation and is not formal GT",
        ],
    })
    assert_no_leaks(original)
    paired = deepcopy(original)
    paired["instance_id"] = "TASK_EXAMPLE_T1_001_VIDEO"
    paired["modality"] = "text_video"
    paired["input"]["current_checkpoint"]["media"] = [deepcopy(media)]
    return original, paired, media


def build_t2():
    left = load(T2_SOURCE_A)
    right = load(T2_SOURCE_B)
    scenario = load(SCENARIO_018)
    depth_index = 5
    candidate = {
        "left": left,
        "right": right,
        "left_index": depth_index,
        "right_index": depth_index,
    }
    shared_media = media_descriptor(
        "IA_PIPE_018--cautious_curiosity",
        "media/talking_head/assets/scenario_018/cautious_curiosity.mp4",
        {
            "facial_expression": "保持警觉但不再催促下结论",
            "gaze": "稳定注视研究员",
            "head_motion": "轻微前倾，等待可验证说明",
            "response_timing": "短暂停顿后追问验证路径",
            "overall_behavior": "在风险边界内重新开放解释空间",
        },
    )
    shared_text = "先别下结论，告诉我这个解释怎么被验证。"
    shared = {
        "current_response": shared_text,
        "observable_cues": ["语气仍克制，但从命令转为要求验证"],
        "observable_expression": deepcopy(shared_media["observable_expression"]),
        "media": [],
    }
    original = build_t2_pair(candidate, shared, scenario["target_state_ids"])
    original["instance_id"] = "TASK_EXAMPLE_T2_001"
    original["input"]["history_a"] = compact_history(left, depth_index)
    original["input"]["history_b"] = compact_history(right, depth_index)
    original["target_spec"].update({
        "direction_labels": ["higher_in_a", "similar", "higher_in_b", "cannot_determine"],
    })
    original["metadata"].update({
        "source_artifacts": [
            str(T2_SOURCE_A.relative_to(ROOT)), str(T2_SOURCE_B.relative_to(ROOT))
        ],
        "source_sha256": [digest(T2_SOURCE_A), digest(T2_SOURCE_B)],
        "shared_observation_text_sha256": hashlib.sha256(shared_text.encode("utf-8")).hexdigest(),
        "shared_media_sha256": digest(ROOT / shared_media["path"]),
        "source_gate_evidence": "historical structurally checked task sources; current formal Gate 3/human review not inherited",
        "codex_full_text_review": "useful_controlled_example_not_formal_release",
        "source_limitations": [
            "both auxiliary histories are six-turn historical trajectories",
            "they demonstrate T2 control but do not satisfy the current main-rollout 10-turn preference",
        ],
    })
    assert_no_leaks(original)
    paired = deepcopy(original)
    paired["instance_id"] = "TASK_EXAMPLE_T2_001_VIDEO"
    paired["modality"] = "text_video"
    paired["input"]["shared_current_observation"]["media"] = [deepcopy(shared_media)]
    return original, paired, shared_media


def build_t3():
    trajectory = load(T1_SOURCE)
    scenario = load(SCENARIO_006)
    turn_index = 4  # t5 checkpoint leaves the required five observed turns
    turn = trajectory["turns"][turn_index]
    actions = [
        {"text": "我先完成制度性问题章节；涉及个人责任的段落等法律意见回来再决定，今天不作定性。"},
        {"text": "现有材料已经足够，我建议保留个人责任段落并按原计划发布，不再等待法律意见。"},
        {"text": "先暂停整篇稿件，补做第二来源的时间链核验；48小时内仍不能确认，就只发布制度性部分。"},
    ]
    checkpoint = {
        **turn,
        "trajectory_id": trajectory["trajectory_id"],
        "scenario_id": trajectory["scenario_id"],
    }
    original = build_t3_candidates(
        checkpoint, actions, delayed_horizon=5,
        target_state_ids=scenario["target_state_ids"],
    )
    original["instance_id"] = "TASK_EXAMPLE_T3_001"
    context = compact_role_context(trajectory["turns"][0])
    original["input"] = {
        **context,
        "history": compact_history(trajectory, turn_index - 1),
        "current_observation": {
            "turn_id": "checkpoint_before_t5",
            "current_response": turn["observation"].get("current_response", ""),
            "observable_cues": deepcopy(turn["observation"].get("observable_cues", [])),
            "observable_expression": deepcopy(turn["observation"].get("observable_expression", {})),
            "media": [],
        },
        "candidate_actions": actions,
    }
    original["target_spec"]["direction_labels"] = [
        "increase", "similar", "decrease", "cannot_determine"
    ]
    original["metadata"].update({
        "source_artifact": str(T1_SOURCE.relative_to(ROOT)),
        "source_sha256": digest(T1_SOURCE),
        "source_gate_evidence": "Scale300 aggregate: machine precheck + model semantic approve; human pending",
        "observed_future_turn_count": len(trajectory["turns"]) - turn_index,
        "example_checkpoint_reason": "three locally executable strategies and a five-turn observed horizon",
        "codex_full_text_review": "usable_example_with_source_limitations",
        "source_limitations": [
            "candidate branches are prediction options; simulator branch validation remains pending",
            "future video is intentionally excluded from prediction input",
        ],
    })
    assert_no_leaks(original)
    return original


def strip_media(instance):
    value = deepcopy(instance)
    value["instance_id"] = "PAIR"
    value["modality"] = "PAIR"
    if value["task_type"] == "T1_state_tracking":
        value["input"]["current_checkpoint"]["media"] = []
    elif value["task_type"] == "T2_history_sensitive_merge":
        value["input"]["shared_current_observation"]["media"] = []
    return value


def build_examples():
    t1, t1_video, t1_media = build_t1()
    t2, t2_video, t2_media = build_t2()
    t3 = build_t3()
    if strip_media(t1) != strip_media(t1_video):
        raise ValueError("T1 text/text+video pair differs outside media")
    if strip_media(t2) != strip_media(t2_video):
        raise ValueError("T2 text/text+video pair differs outside media")
    if t2_video["input"]["shared_current_observation"]["media"][0]["asset_id"] != t2_media["asset_id"]:
        raise ValueError("T2 A/B must share exactly one O* video")
    result = {
        "format": "socialflux_task_examples_v1",
        "status": "task_examples_built_answers_pending",
        "warning": "LLM answers are machine proposals, not human ground truth. ground_truth remains null.",
        "quality_scope": "review examples; not formal benchmark release",
        "examples": [
            {
                "task": "T1",
                "title": "法律复核后编辑的状态推断",
                "text_instance": t1,
                "text_video_instance": t1_video,
                "media": t1_media,
                "llm_answer": None,
                "answer_provenance": None,
            },
            {
                "task": "T2",
                "title": "同一句追问在两段风险历史后的状态差异",
                "text_instance": t2,
                "text_video_instance": t2_video,
                "media": t2_media,
                "llm_answer": None,
                "answer_provenance": None,
            },
            {
                "task": "T3",
                "title": "发布边界三种行动的即时与延迟影响",
                "text_instance": t3,
                "text_video_instance": None,
                "media": {
                    "shown_to_model": False,
                    "reason": "T3 prediction input must not expose action-triggered future video",
                },
                "llm_answer": None,
                "answer_provenance": None,
            },
        ],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _sum_one(values, label):
    if abs(sum(float(v) for v in values.values()) - 1.0) > 1e-6:
        raise ValueError(f"{label} probabilities must sum to 1")


def validate_answer(answer, instance):
    if answer.get("instance_id") != instance["instance_id"]:
        raise ValueError("answer instance_id mismatch")
    target_ids = instance["target_spec"]["target_state_ids"]
    visible_ids = {turn["turn_id"] for turn in instance["input"].get("history", [])}
    if instance["task_type"] == "T1_state_tracking":
        rows = answer.get("predictions", [])
        if len(rows) != len(target_ids) or {row.get("state_id") for row in rows} != set(target_ids):
            raise ValueError("T1 answer must cover every target state exactly once")
        rows[:] = sorted(rows, key=lambda row: target_ids.index(row["state_id"]))
        for row in rows:
            validate_t1_probs(row["intensity_probabilities"])
            validate_t3_probs(row["change_probabilities"])
            if not set(row["evidence_turn_ids"]).issubset(visible_ids):
                raise ValueError("T1 answer references invisible evidence")
            if not 0 <= float(row["confidence"]) <= 1:
                raise ValueError("T1 confidence out of range")
    elif instance["task_type"] == "T2_history_sensitive_merge":
        rows = answer.get("predictions", [])
        if len(rows) != len(target_ids) or {row.get("state_id") for row in rows} != set(target_ids):
            raise ValueError("T2 answer must cover every target state exactly once")
        rows[:] = sorted(rows, key=lambda row: target_ids.index(row["state_id"]))
        ids_a = {turn["turn_id"] for turn in instance["input"]["history_a"]}
        ids_b = {turn["turn_id"] for turn in instance["input"]["history_b"]}
        for row in rows:
            validate_t2_probs(row["direction_probabilities"])
            if not set(row["evidence_a"]).issubset(ids_a) or not set(row["evidence_b"]).issubset(ids_b):
                raise ValueError("T2 answer references invisible evidence")
            if not 0 <= float(row["confidence"]) <= 1:
                raise ValueError("T2 confidence out of range")
    else:
        options = answer.get("options", [])
        expected_options = list(range(len(instance["input"]["candidate_actions"])))
        if len(options) != len(expected_options) or {row.get("action_index") for row in options} != set(expected_options):
            raise ValueError("T3 answer must cover each action exactly once")
        options[:] = sorted(options, key=lambda row: row["action_index"])
        for option in options:
            rows = option.get("state_predictions", [])
            if len(rows) != len(target_ids) or {row.get("state_id") for row in rows} != set(target_ids):
                raise ValueError("T3 answer must cover every target state exactly once")
            rows[:] = sorted(rows, key=lambda row: target_ids.index(row["state_id"]))
            for row in rows:
                validate_t3_probs(row["immediate"])
                validate_t3_probs(row["delayed"])
                if not set(row["evidence_turn_ids"]).issubset(visible_ids):
                    raise ValueError("T3 answer references invisible evidence")
    return answer


def answer_contract(instance):
    target_ids = json.dumps(instance["target_spec"]["target_state_ids"], ensure_ascii=False)
    if instance["task_type"] == "T1_state_tracking":
        shape = '{"instance_id":"%s","predictions":[{"state_id":"...","intensity_probabilities":{"absent":0,"mild":0,"moderate":0,"strong":0,"very_strong":0,"cannot_determine":0},"change_probabilities":{"increase":0,"similar":0,"decrease":0,"cannot_determine":0},"evidence_turn_ids":["t1"],"confidence":0}]}' % instance["instance_id"]
        coverage = "Cover every target state exactly once: " + target_ids
    elif instance["task_type"] == "T2_history_sensitive_merge":
        shape = '{"instance_id":"%s","predictions":[{"state_id":"...","direction_probabilities":{"higher_in_a":0,"similar":0,"higher_in_b":0,"cannot_determine":0},"evidence_a":["t1"],"evidence_b":["t1"],"causal_relevance":["observable causal link"],"confidence":0}]}' % instance["instance_id"]
        coverage = "Cover every target state exactly once: " + target_ids
    else:
        shape = '{"instance_id":"%s","options":[{"action_index":0,"state_predictions":[{"state_id":"...","immediate":{"increase":0,"similar":0,"decrease":0,"cannot_determine":0},"delayed":{"increase":0,"similar":0,"decrease":0,"cannot_determine":0},"evidence_turn_ids":["t1"]}]}]}' % instance["instance_id"]
        coverage = "Cover action_index 0 through %d and every target state exactly once: %s" % (len(instance["input"]["candidate_actions"]) - 1, target_ids)
    reasoning_check = (
        "Compare the target character, not the evaluated agent. Re-check the last two turns of each history before choosing a T2 direction. "
        "For T3, each direction is the candidate action's effect relative to the shared checkpoint, not the absolute state; preserve meaningful strategic differences when the observable evidence supports them. "
        "Use cannot_determine instead of inventing facts."
    )
    if instance["task_type"] == "T3_action_effect_prediction":
        reasoning_check += (
            " In this instance the target explicitly requires legal confirmation before publishing individual-responsibility claims. "
            "Treat an option that publishes such a claim immediately as overriding that observable boundary; do not infer that it calms the target merely because publication is decisive. "
            "Waiting for legal guidance and pausing for additional verification are distinct strategies and need not have identical effects."
        )
    return "\nMandatory output shape; do not use an older format:\n" + shape + "\n" + coverage + ". Every probability object must sum to 1.\n" + reasoning_check


def answer_examples(model_routes_path):
    packet = load(MANIFEST) if MANIFEST.exists() else build_examples()
    route_by_task = {
        "T1": "t1_answer",
        "T2": "t2_answer",
        "T3": "t3_answer",
    }
    model_routes = ModelRoutes.load(model_routes_path).require(route_by_task.values())
    providers = {
        route: build_provider(model_routes.provider_config(route))
        for route in route_by_task.values()
    }
    sampling = {"temperature": 0.1, "top_p": 0.9, "seed": 91501}
    answer_dir = OUTPUT / "llm_answers"
    answer_dir.mkdir(parents=True, exist_ok=True)
    for index, example in enumerate(packet["examples"]):
        route_name = route_by_task[example["task"]]
        provider = providers[route_name]
        instance = example["text_instance"]
        payload = {
            "instance_id": instance["instance_id"],
            "input": instance["input"],
            "target_spec": instance["target_spec"],
        }
        prompt_id = f"task_{example['task'].lower()}_v1"
        prompt = render_prompt(prompt_id, payload) + answer_contract(instance)
        request_start = provider._call_index
        answer = complete_json(
            provider,
            [{"role": "user", "content": prompt}],
            sampling,
            lambda value, instance=instance: validate_answer(value, instance),
            context=f"{example['task']} example answer",
            max_attempts=4,
            retry_guidance="Probability objects must use every listed label exactly once and sum to 1. Evidence IDs must be visible tN IDs.",
        )
        answer_path = answer_dir / f"{example['task'].lower()}_answer.json"
        answer_path.write_text(json.dumps(answer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        example["llm_answer"] = answer
        example["answer_provenance"] = {
            "answer_type": "llm_machine_proposal_not_ground_truth",
            "model_route": route_name,
            **provider.provenance,
            "sampling": sampling,
            "prompt_id": prompt_id,
            "answer_path": str(answer_path.relative_to(ROOT)),
            "answer_sha256": digest(answer_path),
            "actual_request_count": provider._call_index - request_start,
            "human_review": "pending",
        }
        # The paired condition intentionally uses the same proposal/GT contract.
        if example.get("text_video_instance"):
            example["text_video_instance"]["ground_truth"] = None
            example["text_video_answer_policy"] = "same_machine_proposal_for_pairing_demo"
    packet["status"] = "task_examples_built_with_schema_valid_llm_answers"
    packet["answer_models"] = {
        task: providers[route].model
        for task, route in route_by_task.items()
    }
    packet["model_routes_path"] = str(model_routes.source_path)
    packet["model_routes_sha256"] = model_routes.sha256
    packet["actual_llm_request_count"] = sum(
        item["answer_provenance"]["actual_request_count"] for item in packet["examples"])
    MANIFEST.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return packet


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--answer", action="store_true")
    parser.add_argument("--model-routes", type=Path, default=MODEL_ROUTES)
    args = parser.parse_args()
    if not args.build and not args.answer:
        args.build = True
    result = build_examples() if args.build else None
    if args.answer:
        result = answer_examples(args.model_routes)
    print(json.dumps({
        "output": str(MANIFEST.relative_to(ROOT)),
        "status": result["status"],
        "example_count": len(result["examples"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
