#!/usr/bin/env python3
"""Export the saved Fable repeated-evidence false-positive record verbatim."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT / "data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary"
    / "fable_state_only_probe_results.json"
)
DEFAULT_STEM = (
    ROOT / "reports/experiments/2026-10-05_fable_repeated_evidence_failure"
)
CASE_ID = "trust_gpt003_exact_restatement_control"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def extract_payload(full_user_prompt: str):
    marker = "## Input\n\n"
    if marker not in full_user_prompt:
        raise ValueError("state appraisal user prompt has no ## Input payload marker")
    payload_text = full_user_prompt.split(marker, 1)[1]
    return json.loads(payload_text)


def select_record(source: dict):
    original = next(
        row for row in source["rows"]
        if row["case_id"] == CASE_ID
    )
    correction = next(
        row for row in source["pre_provider_corrections"]
        if row["case_id"] == CASE_ID
    )
    result = correction["result"]
    state_appraisal = result["state_appraisal"]
    messages = deepcopy(state_appraisal["request_messages"])
    system_prompt = next(
        message["content"] for message in messages if message["role"] == "system"
    )
    full_user_prompt = next(
        message["content"] for message in messages if message["role"] == "user"
    )
    payload = extract_payload(full_user_prompt)
    target_diagnostic = next(
        item for item in result["calibration"]["state_impacts"]
        if item["variable"] == "relationship.trust"
    )
    target_judgment = result["target_judgment"]
    audit = state_appraisal["provider_audit_records"][0]
    return {
        "format": "socialflux_fable_repeated_evidence_failure_export_v1",
        "case_id": CASE_ID,
        "source_artifact": "data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/fable_state_only_probe_results.json",
        "source_record": {
            "original_row": original,
            "correction_row": correction,
            "correction_reason": correction["correction_reason"],
        },
        "request": {
            "provider_public_config": result["provider_public_config"],
            "sampling": state_appraisal["request_sampling"],
            "messages_as_sent": messages,
            "system_prompt": system_prompt,
            "full_user_prompt_as_sent": full_user_prompt,
            "payload_json": payload,
        },
        "current_state_and_history": {
            "current_pre_update_state": payload["previous_state"],
            "current_pre_update_dynamics": payload["previous_dynamics"],
            "history": payload["memory"],
            "longitudinal_context": payload.get("longitudinal_context"),
            "interaction_ledger": payload["interaction_ledger"],
            "evidence_turn_ids_returned": state_appraisal["evidence_turn_ids"],
        },
        "variable_definitions": {
            "state_variable_paths": payload["state_variable_paths"],
            "dynamics_variable_paths": payload["dynamics_variable_paths"],
            "state_semantics": payload["state_semantics"],
        },
        "model_output": {
            "provider_audit": audit,
            "raw_answer": audit["raw_output"],
            "normalized_appraisal": state_appraisal["appraisal"],
            "state_judgments": state_appraisal["state_judgments"],
            "dynamics_judgments": state_appraisal["dynamics_judgments"],
        },
        "final_update": {
            "evaluation": result["evaluation"],
            "target_judgment": target_judgment,
            "target_calibration_diagnostic": target_diagnostic,
            "target_final_delta": result["evaluation"]["target_delta"],
            "calibration_provenance": {
                key: value for key, value in result["calibration"].items()
                if key not in {"state_impacts", "dynamics_impacts"}
            },
            "full_state_impacts_after_selection": result["calibration"]["state_impacts"],
        },
    }


def markdown(record: dict) -> str:
    request = record["request"]
    state = record["current_state_and_history"]
    definitions = record["variable_definitions"]
    model = record["model_output"]
    update = record["final_update"]
    audit = model["provider_audit"]
    state_text = json.dumps(state, ensure_ascii=False, indent=2)
    definitions_text = json.dumps(definitions, ensure_ascii=False, indent=2)
    update_text = json.dumps(update, ensure_ascii=False, indent=2)
    request_meta = {
        key: value for key, value in request.items()
        if key not in {
            "messages_as_sent", "system_prompt",
            "full_user_prompt_as_sent", "payload_json",
        }
    }
    return f"""# Fable 重复证据误判导出

case_id: {record["case_id"]}

这条记录中，最新 action 与历史中的同一行为逐字重复。Fable 却对
relationship.trust 输出 ordinary_new_evidence / increase，Python 因当前
v7 规则产生 mild_increase，最终 trust +1。

原始来源：{record["source_artifact"]}

## 请求元数据

~~~json
{json.dumps(request_meta, ensure_ascii=False, indent=2)}
~~~

## 实际发送的完整 system prompt

~~~text
{request["system_prompt"]}
~~~

## 实际发送的完整 user prompt（含 payload）

~~~text
{request["full_user_prompt_as_sent"]}
~~~

## 当前 state、历史、变量定义

~~~json
{state_text}
~~~

~~~json
{definitions_text}
~~~

## 模型原始回答

~~~text
{model["raw_answer"]}
~~~

Provider audit 中的结束原因、usage 和原始请求副本：

~~~json
{json.dumps({key: value for key, value in audit.items() if key != "raw_output"}, ensure_ascii=False, indent=2)}
~~~

## 最终更新记录

~~~json
{update_text}
~~~

关键结果：

- Fable judgment: ordinary_new_evidence
- Fable direction: increase
- Fable evidence span: 不能确认，我手头没有足够材料排除线人在采购期间存在利益关联
- Calibration eligibility: eligible
- Calibration selection: selected_valid_new_evidence_immediate
- Final delta: mild_increase（数值上为 trust +1）
- 误判类型：逐字重复的已有坦诚证据被当成当前轮新增 trust 证据
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-stem", type=Path, default=DEFAULT_STEM)
    args = parser.parse_args()
    record = select_record(load(args.input))
    json_path = args.output_stem.with_suffix(".json")
    md_path = args.output_stem.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(markdown(record), encoding="utf-8")
    print(json.dumps({
        "json": str(json_path),
        "markdown": str(md_path),
        "case_id": CASE_ID,
        "raw_prompt_characters": len(record["request"]["full_user_prompt_as_sent"]),
        "raw_answer_characters": len(record["model_output"]["raw_answer"]),
        "target_final_delta": record["final_update"]["target_final_delta"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
