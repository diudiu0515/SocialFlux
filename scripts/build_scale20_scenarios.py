#!/usr/bin/env python3
"""Build the isolated scale20_v1 scenario set from reviewed canonical material.

The builder deliberately changes scenario design/provenance only.  It does not
modify the shared environment, state updater, prompts, or historical evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "configs" / "scenarios"
OUTPUT_ROOT = ROOT / "configs" / "scale20_v1" / "scenarios"


# None means a single continuous interaction.  Otherwise retain only authored
# nodes whose timing already has a public scenario basis.  This removes the old
# uniform five-fragment scaffold without inventing replacement events.
SEGMENT_SELECTION = {
    1: (0, 2, 3),
    2: (0, 2),
    3: (0, 1),
    4: (0, 2),
    5: (0, 1, 2),
    6: None,
    7: (0, 1),
    8: (0, 2),
    9: (0, 1),
    10: (0, 2, 3),
    11: None,
    12: (0, 1, 2),
    13: None,
    14: (0, 2),
    15: (0, 2),
    16: (0, 1, 3),
    17: (0, 1, 2),
    18: (0, 1, 2),
    19: (0, 1, 2),
    20: (0, 1),
}


ADAPTED_SOURCE_OVERRIDES = {
    1: {
        "type": "narrative-derived",
        "provenance_id": "screen-structure-001-the-chair",
        "surface_text_policy": "original_surface_text",
        "redistribution_status": "transformed_structural_abstraction",
        "provenance_note": (
            "High-level academic power and career-dependence structure inspired by "
            "The Chair. The project scenario replaces all characters, institution, "
            "authorship facts, deadlines, choices, and dialogue. Source verification: "
            "https://media.netflix.com/en/only-on-netflix/81206259"
        ),
        "work_title": "The Chair",
        "year": 2021,
        "medium": "television series",
        "related_characters_or_plot_position": (
            "department leadership under institutional pressure; no episode-specific "
            "sequence is claimed"
        ),
    },
    2: {
        "type": "narrative-derived",
        "provenance_id": "screen-structure-002-johnny-keep-walking",
        "surface_text_policy": "original_surface_text",
        "redistribution_status": "transformed_structural_abstraction",
        "provenance_note": (
            "High-level workplace hierarchy, opaque personnel process, and self-protective "
            "management structure inspired by 年会不能停！. The appraisal dispute, evidence, "
            "roles, deadlines, and all dialogue are original. Source verification: "
            "https://society.people.com.cn/n1/2024/0128/c1008-40167927.html"
        ),
        "work_title": "年会不能停！",
        "year": 2023,
        "medium": "film",
        "related_characters_or_plot_position": (
            "an employee is caught in an opaque personnel system while a manager protects "
            "their own position; no scene or dialogue is reproduced"
        ),
    },
    4: {
        "type": "narrative-derived",
        "provenance_id": "screen-structure-004-simple-days",
        "surface_text_policy": "original_surface_text",
        "redistribution_status": "transformed_structural_abstraction",
        "provenance_note": (
            "High-level couple-versus-family-boundary and shared-responsibility structure "
            "inspired by 小日子. The care recipient, appointment, work constraints, roles, "
            "and all dialogue are original. Source verification: "
            "https://wetv.vip/zh-cn/play/ugfajmyp45a2zuk-Simple%20Days"
        ),
        "work_title": "小日子",
        "year": 2024,
        "medium": "television series",
        "related_characters_or_plot_position": (
            "a couple's own decisions become entangled with obligations to both families; "
            "no episode-specific sequence is claimed"
        ),
    },
    5: {
        "type": "narrative-derived",
        "provenance_id": "screen-structure-005-all-is-well",
        "surface_text_policy": "original_surface_text",
        "redistribution_status": "transformed_structural_abstraction",
        "provenance_note": (
            "High-level sibling elder-care, money, and old-family-role structure inspired "
            "by 都挺好. The discharge timeline, capacities, care choices, and all dialogue "
            "are original. Source verification: "
            "https://www.gtv.com.tw/Program/P2020030301/index.html"
        ),
        "work_title": "都挺好",
        "year": 2019,
        "medium": "television series",
        "related_characters_or_plot_position": (
            "siblings with unequal histories negotiate a parent's living and care needs; "
            "the project does not reproduce an episode outcome"
        ),
    },
}


RELATIONSHIP_CATEGORY = {
    1: "学业/导师关系", 2: "职场上下级", 3: "友情", 4: "恋爱/伴侣",
    5: "亲情/手足", 6: "职场合作", 7: "陌生人/平台弱关系", 8: "医患弱关系",
    9: "学业/同伴合作", 10: "职场跨职能", 11: "职场上下级", 12: "恋爱/分居伴侣",
    13: "专业委员会弱关系", 14: "亲情/手足", 15: "职场跨专业",
    16: "亲情兼职场合作", 17: "亲情", 18: "临时跨专业弱关系",
    19: "友情兼创业合作", 20: "职场师徒",
}


CONFLICT_STRUCTURE = {
    1: "贡献证据×制度依赖", 2: "绩效证据×管理权力", 3: "债务履约×友情边界",
    4: "照护容量×被忽视感", 5: "紧急照护×旧家庭不公", 6: "证据强度×公共风险",
    7: "信息不对称×经营损失", 8: "临床不确定×患者价值", 9: "贡献记录×交付责任",
    10: "安全风险×商业时限", 11: "程序公平×赞助压力", 12: "职业迁移×共同照护",
    13: "少数证据×群体定责", 14: "家庭认可×治理条件", 15: "科学不确定×公开预警",
    16: "专业改造×家族遗产", 17: "知情权×保护性隐瞒", 18: "歧义解释×危机升级",
    19: "股权授权×友情背叛", 20: "客户权利×机构生存",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _time_organization(selection: tuple[int, ...] | None, segments: list[dict]) -> str:
    if selection is None:
        return "单次连续互动；允许自然结束，不自动复联"
    kept = [segments[index] for index in selection]
    if len(kept) == 2:
        return f"两次接触：{kept[0]['segment_id']} → {kept[1]['segment_id']}"
    return "三次接触：" + " → ".join(item["segment_id"] for item in kept)


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    matrix = []
    manifest_rows = []

    for index in range(1, 21):
        source_path = SOURCE_ROOT / f"scenario_{index:03d}" / f"scenario_{index:03d}.json"
        scenario = json.loads(source_path.read_text(encoding="utf-8"))
        original_segments = scenario.get("longitudinal_design", {}).get("segments", [])
        selection = SEGMENT_SELECTION[index]

        if index in ADAPTED_SOURCE_OVERRIDES:
            scenario["source"] = ADAPTED_SOURCE_OVERRIDES[index]

        if selection is None:
            scenario.pop("longitudinal_design", None)
        else:
            design = scenario["longitudinal_design"]
            design["segments"] = [original_segments[item] for item in selection]
            # A cap is a safety boundary, not a prescribed fragment length.  Semantic
            # pause/continuation remains the normal transition mechanism.
            for segment in design["segments"]:
                segment["min_turns"] = 1
                segment["max_turns"] = 7

        scenario["construction_status"] = {
            "normalization": "scale20_v1_natural_interaction_design",
            "initial_state": "candidate_pending_human_freeze",
            "quality_gate": "pending_generation_and_semantic_review",
        }
        scenario["quality_gate"] = {
            key: "pending" for key in scenario.get("quality_gate", {})
        }

        target_dir = OUTPUT_ROOT / f"scenario_{index:03d}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"scenario_{index:03d}.json"
        target_path.write_text(
            json.dumps(scenario, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        source = scenario["source"]
        matrix.append({
            "scenario_id": scenario["scenario_id"],
            "title": scenario["title"],
            "relationship_category": RELATIONSHIP_CATEGORY[index],
            "relationship_structure": scenario["narrative_design"]["relationship_structure"],
            "conflict_structure": CONFLICT_STRUCTURE[index],
            "source_type": source["type"],
            "source_work": source.get("work_title"),
            "source_plot_position": source.get("related_characters_or_plot_position"),
            "source_verification": source.get("provenance_note", ""),
            "primary_states": scenario["target_state_ids"],
            "time_organization": _time_organization(selection, original_segments),
            "task_potential": {
                "T1": "check_after_generation",
                "T2": "controlled_pair_design_only_not_two_independent_rollouts",
                "T3": "checkpoint_branch_potential; requires 5-10 subsequent turns",
                "T4": "online_natural_ending_candidate",
            },
            "configuration_status": "schema_check_pending",
            "generation_status": "not_generated",
            "semantic_review_status": "not_reviewed",
        })
        manifest_rows.append({
            "scenario_id": scenario["scenario_id"],
            "title": scenario["title"],
            "source_type": source["type"],
            "source": str(target_path.relative_to(OUTPUT_ROOT)),
            "scenario_sha256": _sha(target_path),
        })

    matrix_path = OUTPUT_ROOT.parent / "design_matrix.json"
    matrix_path.write_text(
        json.dumps({
            "format": "socialflux_scale20_design_matrix_v1",
            "scenario_count": len(matrix),
            "source_target": {"narrative-derived": 14, "synthetic-script": 6},
            "design_contract": {
                "turn_target": "10-20 with natural ending; short retained; 20-turn cap",
                "segment_policy": "scenario-specific only; no uniform fragment count",
                "task_claim_policy": "design potential is not a constructed/checked instance",
            },
            "scenarios": matrix,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest_path = OUTPUT_ROOT / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "format": "socialflux_scale20_scenario_manifest_v1",
            "scenario_count": len(manifest_rows),
            "source_counts": {"narrative-derived": 14, "synthetic-script": 6},
            "design_matrix": str(matrix_path.relative_to(OUTPUT_ROOT.parent)),
            "scenarios": manifest_rows,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(manifest_rows)} scenarios to {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
