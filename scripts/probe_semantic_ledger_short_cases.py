#!/usr/bin/env python3
"""Cheap model probe for quote-grounded appraisal ledger extraction."""

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.appraisal import ModelAppraiser
from environment.interaction_ledger import initial_ledger
from providers.factory import build_provider


ROOT = Path(__file__).resolve().parents[1]
CASES = [
    {
        "id": "proposal",
        "text": "我建议你在14天内先还800元，你看可行吗？",
        "required_any": [["proposal", "open"], ["proposal", "tentative"]],
        "forbidden": [["commitment", "firm"], ["payment", "reported_complete"]],
    },
    {
        "id": "commitment",
        "text": "收到转账后，我会当天确认到账。",
        "required_any": [["commitment", "conditional"], ["commitment", "firm"]],
        "forbidden": [["commitment", "tentative"], ["payment", "reported_complete"]],
    },
    {
        "id": "ambiguous_intention",
        "text": "我初步考虑14天内安排800元，你看是否可行？",
        "required": [["proposal", "tentative"]],
        "forbidden": [["commitment", "firm"], ["payment", "reported_complete"]],
    },
    {
        "id": "payment_report",
        "text": "我刚刚转了800元。",
        "required": [["payment", "reported_complete"]],
        "forbidden": [["commitment", "firm"]],
    },
    {
        "id": "request",
        "text": "你能在14天内还多少？",
        "required": [["request", "open"]],
        "forbidden": [["commitment", "firm"], ["payment", "reported_complete"]],
    },
    {
        "id": "other_owned_requirement",
        "text": "你必须在14天内还300元。",
        "required": [["request", "open"]],
        "required_action_owner": "environment_agent",
        "forbidden": [["commitment", "firm"], ["payment", "reported_complete"]],
    },
    {
        "id": "saved_t2_self_repayment_commitment",
        "text": "我现在能确定的是，14天内至少可以还300元，这个数字应该比较实在。",
        "required_any": [["proposal", "open"], ["proposal", "tentative"]],
        "required_action_owner": "evaluated_agent",
        "forbidden": [["payment", "reported_complete"]],
    },
    {
        "id": "saved_t14_negative_fact_statement",
        "text": "过去21天里确实没有形成可核验的还款承诺，也没有实际到账的金额。",
        "required": [["claim", "reported"]],
        "forbidden": [
            ["request", "open"], ["commitment", "firm"],
            ["payment", "reported_complete"]
        ],
    },
    {
        "id": "saved_t11_boundary_question",
        "text": "根据公开记录，当前的承诺未在21天节点履行，是否意味着我们需要重新明确经济往来的边界？",
        "required": [["request", "open"]],
        "required_action_owner": "environment_agent",
        "forbidden": [["commitment", "firm"], ["payment", "reported_complete"]],
    },

    {
        "id": "pure_acceptance_no_new_event",
        "text": "我接受你提出的普通联系方式。",
        "forbidden": [
            ["proposal", "open"], ["proposal", "tentative"],
            ["commitment", "firm"], ["commitment", "conditional"],
            ["request", "open"], ["payment", "reported_complete"]
        ],
    },
    {
        "id": "acceptance_restatement_no_new_event",
        "text": "我接受这个提议。在现有分歧未解决前，我们保持普通朋友联系。",
        "active_proposal": "在现有分歧未解决前，只保持普通朋友联系。",
        "forbidden": [
            ["proposal", "open"], ["proposal", "tentative"],
            ["commitment", "firm"], ["commitment", "conditional"],
            ["request", "open"], ["payment", "reported_complete"]
        ],
    },

    {
        "id": "saved_t15_contact_acceptance",
        "text": "我接受这个模式，就按你说的方式保持联系。",
        "required": [["commitment", "firm"]],
        "required_action_owner": "evaluated_agent",
        "forbidden": [["request", "open"], ["payment", "reported_complete"]],
    },
    {
        "id": "pause",
        "text": "今天先谈到这里，旧账责任不变。",
        "required": [["pause", "explicit"]],
        "forbidden": [["commitment", "firm"], ["payment", "reported_complete"]],
    },
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", dest="case_ids")
    args = parser.parse_args()
    config = json.loads(
        (ROOT / "configs/r3_agent_model_ablation.local.json").read_text(encoding="utf-8")
    )
    scenario = json.loads(
        (ROOT / "configs/scenarios/scenario_003/scenario_003.json").read_text(encoding="utf-8")
    )
    provider = build_provider(config["environment"]["provider"])
    appraiser = ModelAppraiser(
        scenario,
        provider,
        {**config["environment"].get("sampling", {}), "temperature": 0},
        prompt_id="environment_appraisal_v11",
    )
    selected_cases = [
        case for case in CASES
        if not args.case_ids or case["id"] in set(args.case_ids)
    ]
    if not selected_cases:
        raise ValueError("no matching short probe cases")
    rows = []
    for case in selected_cases:
        try:
            result = appraiser.appraise(
                action={"text": case["text"]},
                previous_state=scenario["initial_state"],
                previous_dynamics=scenario["initial_dynamics"],
                memory={
                    "relevant_turn_ids": [], "events": [],
                    "deterministic_surface_duplicate_ids": [],
                },
                longitudinal_context={
                    "segment": {"live_questions": []},
                    "public_timeline": [],
                },
                interaction_ledger=initial_ledger(
                    scenario["background"],
                    scenario["evaluated_agent_role"]["explicit_goal"],
                    scenario["narrative_design"]["meaningful_choice_space"],
                ),
            )
            events = result["appraisal"]["ledger_events"]
            signatures = {
                (event["event_type"], event["status"]) for event in events
            }
            missing = [pair for pair in case.get("required", []) if tuple(pair) not in signatures]
            required_any = case.get("required_any", [])
            if required_any and not any(tuple(pair) in signatures for pair in required_any):
                missing.append({"any_of": required_any})
            required_action_owner = case.get("required_action_owner")
            owner_signatures = case.get("required", []) + required_any
            owner_match = (
                required_action_owner is None
                or any(
                    event["action_owner"] == required_action_owner
                    and [event["event_type"], event["status"]] in owner_signatures
                    for event in events
                )
            )
            forbidden = [pair for pair in case["forbidden"] if tuple(pair) in signatures]
            rows.append({
                **case,
                "passed": not missing and not forbidden and owner_match,
                "missing_required": missing,
                "present_forbidden": forbidden,
                "required_action_owner_matched": owner_match,
                "model_events": events,
                "social_act": result["appraisal"]["social_act"],
            })
        except Exception as exc:
            rows.append({
                **case,
                "passed": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "error_diagnostics": list(getattr(exc, "diagnostics", [])),
            })
    passed = sum(row["passed"] for row in rows)
    output = {
        "format": "socialflux_semantic_ledger_short_probe_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "quality_version": "r3_semantic_ledger_v29",
        "review_status": "automatic_model_probe_not_human_validation",
        "prompt_id": "environment_appraisal_v11",
        "model": config["environment"]["provider"]["model"],
        "case_count": len(rows),
        "passed_case_count": passed,
        "pass_rate": round(passed / len(rows), 4),
        "actual_provider_requests": getattr(provider, "_call_index", None),
        "cases": rows,
    }
    suffix = "_" + "_".join(args.case_ids) if args.case_ids else ""
    target = ROOT / f"build/r3_semantic_ledger_v29/short_appraisal_probe{suffix}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        key: output[key] for key in (
            "quality_version", "case_count", "passed_case_count", "pass_rate",
            "actual_provider_requests",
        )
    }, ensure_ascii=False))
    for row in rows:
        print(json.dumps({
            "id": row["id"], "passed": row["passed"],
            "events": row.get("model_events"), "error": row.get("error"),
        }, ensure_ascii=False))
    print(target)


if __name__ == "__main__":
    main()
