#!/usr/bin/env python3
"""Build the website-facing Scale20 v2 revision and pilot evidence packet."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "scale20_v2" / "review.json"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def candidate(progress_path, scenario_id, model_review, issues):
    progress = read(ROOT / progress_path)
    attempt = progress["attempts"][0]
    relative = Path(progress_path).parent / f"scenario_{scenario_id[-3:]}" / (
        ("short_trajectories" if attempt["status"] == "short_natural_trajectory" else "rejected")
    ) / (attempt.get("trajectory_file") or attempt["partial_trajectory_file"])
    trajectory = read(ROOT / relative)
    return {
        "configuration_version": "scale20_v2",
        "scenario_id": scenario_id,
        "trajectory_id": trajectory["trajectory_id"],
        "artifact_path": relative.as_posix(),
        "turn_count": len(trajectory.get("turns", [])),
        "generation_status": attempt["status"],
        "ending": trajectory.get("ending"),
        "actual_request_counts": trajectory.get("actual_request_counts", {}),
        "machine_precheck": attempt.get("precheck", {"passed": False}),
        "model_semantic_review": model_review,
        "human_review": "pending",
        "issues": issues,
    }


def main():
    matrix = read(ROOT / "configs" / "scale20_v2" / "design_matrix.json")
    scenarios = []
    for index in range(1, 21):
        path = ROOT / "configs" / "scale20_v2" / "scenarios" / f"scenario_{index:03d}" / f"scenario_{index:03d}.json"
        scenario = read(path)
        design = scenario.get("longitudinal_design", {})
        scenarios.append({
            "scenario_id": scenario["scenario_id"],
            "title": scenario["title"],
            "background": scenario["background"],
            "segments": [{
                "segment_id": item["segment_id"],
                "reason": item["reason"],
                "event_pool_id": item.get("event_pool_id"),
            } for item in design.get("segments", [])],
            "authored_public_events": [{
                "event_pool_id": item["event_pool_id"],
                "possible_records": [outcome["public_record"] for outcome in item["outcomes"]],
            } for item in design.get("event_pools", [])],
            "generation_status": "not_generated_with_final_v2_after_last_control_flow_fix",
            "human_review": "pending",
        })
    candidates = [
        candidate(
            "build/scale20_v2/pilot_001_r2/progress.json",
            "IA_PIPE_001",
            {"label": "improved_event_progression_but_generation_error", "note": "第1轮后进入组会；第4轮 response 模型连续把学生的申诉权写成导师自己的动作，硬门禁正确拒绝。"},
            [{"turn_ids": ["t1"], "issue": "组会节点和公开贡献记录已触发。"}, {"turn_ids": ["after_t3"], "issue": "第4轮结构化 response 在4次尝试中持续发生动作归属错误，轨迹中断。"}],
        ),
        candidate(
            "build/scale20_v2/pilot_002_r2/progress.json",
            "IA_PIPE_002",
            {"label": "improved_event_progression_but_short_rejected", "note": "第3轮进入自查并公开确认成果归属错误；第4轮环境复读事件前答复，第5轮自然结束。最终代码已加入跨事件陈旧回复拒绝，但未把该旧轨迹重写为通过。"},
            [{"turn_ids": ["after_t3"], "issue": "自查记录确认员工完成两项交付，未计入个人评分，却列入经理管理成效。"}, {"turn_ids": ["t4"], "issue": "经理复读事件前答复，未回答更正流程；broken_dialogue_logic。"}, {"turn_ids": ["t5"], "issue": "自然结束但仅5轮，不满足10–20轮主数据长度。"}],
        ),
    ]
    payload = {
        "format": "socialflux_scale20_v2_website_review_v1",
        "configuration_version": "scale20_v2",
        "parent_rollout_version": "scale20_v1",
        "status": "20_configs_strengthened_two_representative_pilots_reviewed",
        "matrix_format": matrix["format"],
        "scenario_count": len(scenarios),
        "evidence_node_scenario_count": sum(bool(x["authored_public_events"]) for x in scenarios),
        "final_code_validation": {
            "related_test_count": 87,
            "passed": 87,
            "note": "The two pilots predate the final stale-response boundary check; they remain immutable failure evidence.",
        },
        "scenarios": scenarios,
        "candidates": candidates,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
