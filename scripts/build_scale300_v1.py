#!/usr/bin/env python3
"""Build Scale300 by preserving Scale200 and adding 100 new scenarios.

The extension contains twenty mechanism families with five relationship variants
each: fourteen narrative-derived families and six original families.  Design-card
generation uses the same bounded prompt, normalization, ontology, and schema as
Scale200.  Existing Scale200 JSON artifacts are copied byte-for-byte.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_scale200_v1 as base
from schemas.validate import validate_scenario
from scripts.scenario_docs import write_catalog, write_document


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "configs" / "scale200_v1" / "scenarios"
PARENT_MATRIX = ROOT / "configs" / "scale200_v1" / "design_matrix.json"
OUTPUT = ROOT / "configs" / "scale300_v1" / "scenarios"
CACHE = ROOT / "build" / "scale300_v1" / "design_generation"


NARRATIVE_FAMILIES = [
    ("midlife_income_dignity", "凡人歌", 2024, "television series", "中年收入波动、家庭尊严与职业选择"),
    ("neighborhood_education_resources", "小巷人家", 2024, "television series", "邻里资源、子女教育与长期人情边界"),
    ("reform_team_loyalty", "大江大河之岁月如歌", 2024, "television series", "组织改革、同事情义与责任证据"),
    ("business_information_trust", "繁花", 2023, "television series", "商业信息不对称、旧关系与退出风险"),
    ("cross_team_medical_duty", "欢迎来到麦乐村", 2023, "television series", "跨团队医疗协作、专业判断与照护责任"),
    ("newsroom_credit_ethics", "新闻女王", 2023, "television series", "新闻判断、职业竞争与署名责任"),
    ("intimacy_care_autonomy", "春色寄情人", 2024, "television series", "亲密照护、身体自主与返乡选择"),
    ("family_ambition_control", "承欢记", 2024, "television series", "家庭期待、职业资源与个人生活边界"),
    ("public_enforcement_empathy", "执行法官", 2024, "television series", "规则执行、现实困难与程序信任"),
    ("duty_family_cost", "三大队", 2023, "television series", "长期责任、家庭代价与未完成目标"),
    ("local_governance_accountability", "县委大院", 2022, "television series", "公共治理、基层压力与可核验责任"),
    ("community_policing_trust", "警察荣誉", 2022, "television series", "社区冲突、同事判断与弱关系信任"),
    ("mediation_principle_relationship", "底线", 2022, "television series", "原则判断、调解压力与持续合作"),
    ("talent_parental_choice", "天才基本法", 2022, "television series", "天赋期待、亲子选择与学业自主"),
]

ORIGINAL_FAMILIES = [
    ("eldercare_technology_consent", "远程照护技术、老人同意与子女风险判断"),
    ("creator_audience_boundary", "内容创作者、观众期待与私人边界"),
    ("cofounder_exit_transition", "共同创业、退出交接与关系债务"),
    ("accessibility_shared_space", "公共空间无障碍、邻里成本与程序公平"),
    ("medical_data_consent", "健康数据授权、研究价值与可撤回同意"),
    ("gig_work_coordination", "临时用工协作、平台记录与弱关系责任"),
]


def family_records():
    records = []
    for family_id, work, year, medium, mechanism in NARRATIVE_FAMILIES:
        records.append({
            "family_id": family_id,
            "source_type": "narrative-derived",
            "source_work": work,
            "year": year,
            "medium": medium,
            "mechanism": mechanism,
        })
    for family_id, mechanism in ORIGINAL_FAMILIES:
        records.append({
            "family_id": family_id,
            "source_type": "synthetic-script",
            "source_work": None,
            "year": None,
            "medium": "original scenario",
            "mechanism": mechanism,
        })
    return records


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def scale300_scenario(index, family, card):
    scenario = base._build_scenario(index, family, card)
    source = scenario.get("source", {})
    provenance_id = source.get("provenance_id", "")
    source["provenance_id"] = provenance_id.replace("scale200-", "scale300-")
    scenario["media_generation"]["note"] = (
        "Scale300 本轮先验证文本互动；通过 Gate 3 后沿用既定多模态方案。"
    )
    scenario["construction_status"]["normalization"] = (
        "scale300_v1_extension_card_and_state_alignment"
    )
    scenario["scenario_design_revision"].update({
        "version": "scale300_v1_extension_content_normalized",
        "design_model": "Qwen/Qwen3-32B-AWQ",
    })
    scenario["sampling_plan"]["seed"] = 30000 + index
    validate_scenario(scenario)
    return scenario


def row_for(scenario, family, index):
    row = base._row(scenario, family, index)
    row["generation_status"] = "not_generated_with_scale300_v1"
    return row


def copy_parent(rows):
    mismatches = []
    for index in range(1, 201):
        source = PARENT / f"scenario_{index:03d}" / f"scenario_{index:03d}.json"
        target_dir = OUTPUT / f"scenario_{index:03d}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"scenario_{index:03d}.json"
        shutil.copyfile(source, target)
        write_document(target)
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(target.read_bytes()).digest():
            mismatches.append(index)
    if mismatches:
        raise AssertionError(f"Scale200 byte mismatches: {mismatches}")
    return rows


def build_catalog():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    parent_matrix = json.loads(PARENT_MATRIX.read_text(encoding="utf-8"))
    rows = copy_parent(deepcopy(parent_matrix["scenarios"]))
    seen_titles = {item["title"] for item in rows}
    index = 201
    for family in family_records():
        cached = json.loads((CACHE / f"{family['family_id']}.json").read_text(encoding="utf-8"))
        cards = [base._normalize_runtime_card(deepcopy(item)) for item in cached["cards"]]
        base._validate_cards(cards)
        for source_card in cards:
            card = deepcopy(source_card)
            if card["title"] in seen_titles:
                card["title"] = f"{card['title']}｜{card['evaluated_role']}—{card['environment_role']}"
            if card["title"] in seen_titles:
                card["title"] = f"{card['title']}（{index:03d}）"
            scenario = scale300_scenario(index, family, card)
            seen_titles.add(scenario["title"])
            target_dir = OUTPUT / f"scenario_{index:03d}"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"scenario_{index:03d}.json"
            target.write_text(
                json.dumps(scenario, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            write_document(target)
            rows.append(row_for(scenario, family, index))
            index += 1
    if index != 301:
        raise AssertionError(f"expected final index 301, got {index}")
    write_catalog(OUTPUT)
    source_counts = {}
    relation_counts = {}
    for row in rows:
        source_counts[row["source_type"]] = source_counts.get(row["source_type"], 0) + 1
        relation_counts[row["relationship_category"]] = relation_counts.get(row["relationship_category"], 0) + 1
    matrix = {
        "format": "socialflux_scale300_design_matrix_v1",
        "scenario_count": len(rows),
        "parent": "configs/scale200_v1",
        "design_contract": {
            **parent_matrix.get("design_contract", {}),
            "scenario_content_revision": (
                "v3: Scale200 preserved; 100 additional bounded evidence scenarios"
            ),
            "automatic_gate_policy": (
                "machine checks produce proposals only; every human attestation remains pending"
            ),
        },
        "source_counts": source_counts,
        "new100_source_counts": {
            "narrative-derived": 70,
            "synthetic-script": 30,
        },
        "relationship_counts": relation_counts,
        "scenarios": rows,
    }
    atomic_json(OUTPUT.parent / "design_matrix.json", matrix)
    return matrix


def write_rollout_configs():
    base_config = json.loads(
        (ROOT / "configs" / "scale200_v1" / "rollout.shard1.local.json").read_text(
            encoding="utf-8"
        )
    )
    for shard in range(4):
        endpoint = f"http://127.0.0.1:{8301 + shard}/v1/chat/completions"
        config = deepcopy(base_config)
        for provider in (
            config["environment"]["provider"],
            config["environment"]["response_provider"],
            config["construction"]["provider"],
            config["policies"][0]["provider"],
            config["policies"][0]["environment_provider_override"],
            config["policies"][0]["environment_response_provider_override"],
        ):
            provider["endpoint"] = endpoint
            # Qwen3 thinking must be disabled for JSON-first structured appraisal.
            provider["chat_template_kwargs"] = {"enable_thinking": False}
        policy = config["policies"][0]
        policy["policy_id"] = f"qwen3_32b_scale300_all_stages_shard_{shard + 1}"
        policy["sampling"]["seed"] = 30201 + shard
        config.pop("scale200_shard", None)
        config["scale300_shard"] = {
            "index": shard + 1,
            "count": 4,
            "scenario_rule": f"201 <= ordinal <= 300 and (ordinal - 1) % 4 == {shard}",
            "candidate_budget_per_scenario": 1,
            "retain_all_attempts": True,
        }
        atomic_json(OUTPUT.parent / f"rollout.shard{shard + 1}.local.json", config)

    # Reproduce the Scale200 best-performing topology: Qwen32 policy and a
    # separate Qwen3.5 environment.
    for shard in range(4):
        parent = (
            ROOT / "configs" / "scale200_v1"
            / f"rollout.hybrid.shard{shard + 1}.local.json"
        )
        config = json.loads(parent.read_text(encoding="utf-8"))
        policy = config["policies"][0]
        policy["policy_id"] = (
            f"qwen32_policy_qwen35_env_scale300_shard_{shard + 1}"
        )
        policy["sampling"]["seed"] = 30301 + shard
        for provider in (
            config["environment"]["provider"],
            config["environment"]["response_provider"],
            config["construction"]["provider"],
            policy["provider"],
        ):
            provider["chat_template_kwargs"] = {"enable_thinking": False}
        config.pop("scale200_shard", None)
        config["scale300_shard"] = {
            "index": shard + 1,
            "count": 4,
            "scenario_rule": (
                f"201 <= ordinal <= 300 and (ordinal - 1) % 4 == {shard}"
            ),
            "candidate_budget_per_scenario": 1,
            "retain_all_attempts": True,
        }
        atomic_json(
            OUTPUT.parent / f"rollout.hybrid.shard{shard + 1}.local.json",
            config,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", action="append", default=[])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retry-limit", type=int, default=3)
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    endpoints = args.endpoint or [
        "http://127.0.0.1:8301", "http://127.0.0.1:8302",
        "http://127.0.0.1:8303", "http://127.0.0.1:8304",
    ]
    if not args.build_only:
        # Set the shared versioned cache once before threads start.
        base.CACHE = CACHE
        pending = [
            family for family in family_records()
            if not (CACHE / f"{family['family_id']}.json").exists()
        ]
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    base._generate_family,
                    family,
                    endpoints[index % len(endpoints)],
                    args.retry_limit,
                ): family
                for index, family in enumerate(pending)
            }
            for future in as_completed(futures):
                family_id, status, target = future.result()
                print(f"{status}: {family_id} -> {target}", flush=True)
    matrix = build_catalog()
    write_rollout_configs()
    print(json.dumps({
        "scenario_count": matrix["scenario_count"],
        "source_counts": matrix["source_counts"],
        "output": str(OUTPUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
