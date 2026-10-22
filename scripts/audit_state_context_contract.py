#!/usr/bin/env python3
"""No-model audit for the v3.2.24 state request context boundary."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.appraisal_context import build_appraisal_context
from environment.public_situation import render_public_background
from prompts.loader import get_prompt, prompt_manifest
from rollout.configuration import load_rollout_config

OUTPUT = ROOT / (
    "data/gpt50/experiment/state_v3_validation/"
    "v323_state_judgment_primary/context_contract_audit_v724.json"
)
CONFIG = ROOT / (
    "configs/gpt50_experiment/"
    "rollout.state_independent_per_variable_v3_state_judgment_primary_candidate.json"
)


def main():
    history = [
        {"turn_id": 1, "role": "evaluated_agent", "text": "先分阶段刊出，并标注待核实。"},
        {"turn_id": 1, "role": "environment_agent", "text": "这会怎样处理来源冲突？"},
        {"turn_id": 2, "role": "evaluated_agent", "text": "我不能确认来源没有利益关联。"},
        {"turn_id": 2, "role": "environment_agent", "text": "请具体说明今晚的写法。"},
    ]
    action = {"text": "我不能确认来源没有利益关联。"}
    turns = [
        {"turn_id": "t1", "state_judgments": [], "numeric_state_delta": {"relationship": {"trust": "similar"}}},
        {"turn_id": "t2", "state_judgments": [{
            "variable": "relationship.trust", "judgment": "ordinary_new_evidence",
            "direction": "increase", "evidence_span": "不能确认来源没有利益关联",
        }], "numeric_state_delta": {"relationship": {"trust": "mild_increase"}}},
    ]
    ledger = {"unresolved_threads": [{"text": "请具体说明今晚的写法。"}], "latest_obligation": None}
    context = build_appraisal_context(
        history=history, turns=turns, action=action, current_turn_id=3,
        interaction_ledger=ledger, longitudinal_context={"segment": {"live_questions": []}},
    )
    background = {
        "background": "当前发布窗口很短。",
        "narrative_design": {
            "relationship_structure": "editor and reporter",
            "power_structure": "each controls a resource",
            "goal_conflict": "publish or verify",
            "relevant_history": [
                "A records release scheduled for Monday later confirms the waiver and complicates the allegation.",
            ],
        },
    }
    rendered = render_public_background(background)
    prompt = get_prompt("environment_state_appraisal_v3_variable_evidence_primary")
    config = load_rollout_config(CONFIG)
    checks = {
        "current_turn_explicit": context["current_turn"]["turn_id"] == "t3",
        "historical_turns_explicit": len(context["historical_turns"]) == 2,
        "latest_unanswered_question_explicit": context["latest_unanswered_question"] == "请具体说明今晚的写法。",
        "duplicate_match_after_final_action": len(context["duplicate_evidence_matches"]) == 1,
        "duplicate_match_has_no_numeric_delta_dependency": (
            "prior_numeric_update" in context["state_evidence_history"][0]
            and "prior_numeric_update" in context["state_evidence_history"][1]
        ),
        "future_outcome_removed": "later confirms" not in rendered and "complicates the allegation" not in rendered,
        "future_schedule_retained": "scheduled for Monday" in rendered,
        "old_slow_no_update_rule_removed": "will not update a slow variable" not in prompt,
        "immediate_rule_present": "Every valid ordinary or decisive new-evidence judgment is immediately eligible" in prompt,
        "runtime_revision_v724": config["environment"].get("state_transition_runtime_revision") == "v3.2.24",
        "manifest_matches_prompt": prompt_manifest()["prompts"]["environment_state_appraisal_v3_variable_evidence_primary"]["sha256"] == hashlib.sha256(prompt.encode()).hexdigest(),
    }
    result = {
        "format": "socialflux_state_context_contract_audit_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(CONFIG.relative_to(ROOT)),
        "checks": checks,
        "passed": all(checks.values()),
        "context_sample": context,
        "rendered_background": rendered,
        "prompt_id": "environment_state_appraisal_v3_variable_evidence_primary",
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "passed": result["passed"], "failed_checks": [k for k, v in checks.items() if not v]}, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
