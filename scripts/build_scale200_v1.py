#!/usr/bin/env python3
"""Generate and build 200 versioned SocialFlux scenario configurations.

The first 150 scenarios are copied byte-for-byte from scale150_v1. The remaining
50 are built from ten extension mechanism families (five cards each),
then deterministically normalized into the existing scenario schema.  Design
generation is resumable: every family response is written before the catalog is
built, and no rollout artifact is touched.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.factory import build_provider
from schemas.validate import validate_scenario
from scripts.scenario_docs import write_catalog, write_document


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "configs" / "scale20_v2" / "scenarios"
PARENT = ROOT / "configs" / "scale150_v1" / "scenarios"
PARENT_MATRIX = ROOT / "configs" / "scale150_v1" / "design_matrix.json"
OUTPUT = ROOT / "configs" / "scale200_v1" / "scenarios"
CACHE = ROOT / "build" / "scale200_v1" / "design_generation"


NARRATIVE_FAMILIES = [
    ("workplace_credit", "年会不能停！", 2023, "film", "绩效归属、层级自保与不透明流程"),
    ("family_care", "都挺好", 2019, "television series", "养老责任、旧家庭不公与资源边界"),
    ("couple_family_boundary", "小日子", 2024, "television series", "伴侣共同体、原生家庭介入与住房压力"),
    ("friendship_status", "三十而已", 2020, "television series", "友情、社会地位与资源不对称"),
    ("career_dependency", "我的前半生", 2017, "television series", "职业转型、帮助边界与情感依赖"),
    ("image_authenticity", "装腔启示录", 2023, "television series", "形象管理、亲密诚实与职业风险"),
    ("intimate_autonomy", "玫瑰的故事", 2024, "television series", "个人自主、亲密期待与人生选择"),
    ("child_medical_care", "亲爱的小孩", 2022, "television series", "儿童照护、医疗不确定与重组家庭协作"),
    ("dignified_support", "我在他乡挺好的", 2021, "television series", "朋友支持、个人尊严与城市生存压力"),
    ("professional_client", "平凡之路", 2023, "television series", "职业伦理、客户目标与团队责任"),
    ("disclosure_power", "不完美受害人", 2023, "television series", "事实披露、舆论压力与权力不对称"),
    ("clinical_disagreement", "问心", 2023, "television series", "医疗判断、患者价值与同事分歧"),
    ("finance_compliance", "城中之城", 2024, "television series", "金融合规、职业忠诚与客户损失"),
    ("project_accountability", "理想之城", 2021, "television series", "项目责任、证据链与组织政治"),
    ("loyalty_legal_boundary", "狂飙", 2023, "television series", "亲友情义、利益网络与法律边界"),
    ("old_harm_evidence", "漫长的季节", 2023, "television series", "旧日伤害、残缺证据与迟到责任"),
    ("emergency_coordination", "开端", 2022, "television series", "紧急协作、重复判断与责任归属"),
    ("community_change", "去有风的地方", 2023, "television series", "社区发展、外来方案与本地信任"),
    ("intergenerational_duty", "人世间", 2022, "television series", "代际照护、家庭财产与长期责任"),
    ("mother_daughter_control", "烟火人家", 2024, "television series", "母女控制、生活选择与关系边界"),
    ("career_intimacy_boundary", "以爱为营", 2023, "television series", "职业资源、亲密关系与利益边界"),
    ("financial_loyalty", "追风者", 2024, "television series", "职业伦理、金融风险与组织忠诚"),
    ("rural_education_duty", "山花烂漫时", 2024, "television series", "教育责任、资源边界与长期承诺"),
    ("friendship_mutual_aid", "好东西", 2024, "film", "友情及弱关系临时互助、边界协商与退出选择"),
    ("care_career_allocation", "我们的婚姻", 2022, "television series", "家庭照护、职业机会与伴侣公平"),
]

ORIGINAL_FAMILIES = [
    ("academic_evidence", "学术合作中的贡献、方法争议与职业依赖"),
    ("platform_accountability", "平台规则、交易证据与弱关系责任"),
    ("debt_boundary", "借贷履约、关系边界与现实困难"),
    ("community_allocation", "共同资源分配、程序公平与邻里关系"),
    ("distance_planning", "异地安排、共同责任与承诺可信度"),
    ("scientific_uncertainty", "科学不确定、公开沟通与决策时限"),
    ("ai_safety", "AI 安全、商业压力与可逆上线策略"),
    ("creative_rights", "创作贡献、授权边界与合作关系"),
    ("shared_housing_boundary", "合租责任、生活边界与弱关系信任"),
    ("volunteer_governance", "志愿协作、程序公平与退出责任"),
    ("data_authorship", "数据贡献、署名边界与研究合作风险"),
]

EXTENSION_FAMILY_IDS = (
    "intergenerational_duty", "mother_daughter_control",
    "career_intimacy_boundary", "financial_loyalty",
    "rural_education_duty", "friendship_mutual_aid",
    "care_career_allocation", "shared_housing_boundary",
    "volunteer_governance", "data_authorship",
)


def _family_records():
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


def _extension_family_records():
    by_id = {item["family_id"]: item for item in _family_records()}
    return [by_id[family_id] for family_id in EXTENSION_FAMILY_IDS]


CARD_KEYS = {
    "title", "relationship_category", "environment_role", "evaluated_role",
    "background", "relevant_history", "environment_hidden_intention",
    "environment_goal", "evaluated_goal", "key_fact_boundaries",
    "meaningful_choices", "initial_reason", "initial_goal",
    "initial_live_questions", "initial_pause_when", "evidence_after_days",
    "evidence_record", "evidence_opening", "evidence_goal",
    "evidence_live_questions", "evidence_pause_when", "decision_after_days",
    "decision_record", "decision_opening", "decision_goal",
    "decision_live_questions", "natural_endings", "primary_states",
}


RELATION_TARGETS = [
    "亲情或家庭", "友情", "恋爱或伴侣", "学业或职场合作", "陌生人或弱关系",
]


def _prompt(family, slot):
    source = (
        f"影视结构参考《{family['source_work']}》。只借鉴高层关系和冲突机制；"
        "不得复制角色、对白、具体事件顺序或结局，不得声称具体集数。"
        if family["source_type"] == "narrative-derived"
        else "这是原创机制组，不得暗示来自任何具体影视作品。"
    )
    return f"""为 SocialFlux 设计一个社会互动场景。只输出一个 JSON 对象，不要数组、markdown、解释或思维过程。
机制：{family['mechanism']}
{source}
关系必须以“{RELATION_TARGETS[slot]}”为核心。场景须有双方合理诉求、真实取舍、信息不对称和可观察后果，能自然支持10–20轮；不得写逐轮剧本、强制和解或用重复确认凑长度。
公开证据节点必须预先有理由发生，只确认有限事实；时间到不等于履约，人物报告不等于核验完成。背景不得依赖模型临场编造制度、权力、金额、诊断或结果。
每个字符串不超过90个汉字。对象必须且只能包含：
title, relationship_category, environment_role, evaluated_role, background,
relevant_history(恰好3条), environment_hidden_intention, environment_goal,
evaluated_goal, evidence_after_days(1到7整数), evidence_record,
decision_after_days(1到14整数), decision_record。
只输出合法 JSON。"""


def _parse_json_object(text):
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model response does not contain a JSON object")
    return json.loads(cleaned[start:end + 1])


COMPACT_KEYS = {
    "title", "relationship_category", "environment_role", "evaluated_role",
    "background", "relevant_history", "environment_hidden_intention",
    "environment_goal", "evaluated_goal", "evidence_after_days",
    "evidence_record", "decision_after_days", "decision_record",
}


def _validate_compact(card):
    if not isinstance(card, dict) or set(card) != COMPACT_KEYS:
        raise ValueError(f"invalid compact keys: {sorted(set(card) ^ COMPACT_KEYS)}")
    if not isinstance(card["relevant_history"], list) or len(card["relevant_history"]) != 3:
        raise ValueError("compact relevant_history must contain three items")
    if not 1 <= card["evidence_after_days"] <= 7:
        raise ValueError("evidence_after_days outside 1..7")
    if not 1 <= card["decision_after_days"] <= 14:
        raise ValueError("decision_after_days outside 1..14")
    scalar_keys = COMPACT_KEYS - {
        "relevant_history", "evidence_after_days", "decision_after_days"
    }
    if any(not isinstance(card[key], str) or not card[key].strip() for key in scalar_keys):
        raise ValueError("compact scalar fields, including evidence/decision records, must be non-empty strings")


def _render_record_part(value):
    if isinstance(value, str) and value.strip():
        return value.strip().rstrip("。；; ")
    if isinstance(value, list):
        items = [_render_record_part(item) for item in value]
        return "、".join(item for item in items[:3] if item)
    if isinstance(value, dict):
        items = [
            f"{str(key).strip()}（{_render_record_part(item)}）"
            for key, item in value.items()
            if str(key).strip() and _render_record_part(item)
        ]
        return "；".join(items)
    text = str(value).strip()
    return text.rstrip("。；; ") if text else ""


def _render_public_record(value):
    """Render one bounded authored record without leaking Python containers."""
    if isinstance(value, str) and value.strip():
        return value.strip().rstrip("。；; ")
    rendered = _render_record_part(value)
    if not rendered:
        raise ValueError("evidence record is empty")
    label = "公开记录分项载明：" if isinstance(value, dict) else "公开记录载明："
    return label + rendered


def _normalize_runtime_card(card):
    """Repair legacy model-card shapes while preserving their authored content."""
    value = deepcopy(card)
    evidence = _render_public_record(value["evidence_record"])
    title = str(value["title"]).strip()
    days = int(value["evidence_after_days"])
    value["evidence_record"] = evidence
    value["decision_record"] = (
        f"围绕“{title}”，双方到了重新决定继续、附条件继续、暂停或退出的节点；"
        "节点本身不预设任何选择、承诺或完成结果。"
    )
    value["relevant_history"] = list(value["relevant_history"][:3]) + [
        f"双方已知{days}天后会出现一项预设公开记录并再次联系；"
        "该约定不证明任何行动届时已经完成。"
    ]
    value["key_fact_boundaries"] = [
        "当前只把公开背景和明确历史视为既有事实，不把提案写成承诺。",
        f"后续公开记录最多确认其明示内容：{evidence}",
        "人物陈述属于行为报告；只有公开记录明示的结果才算可核验结果。",
        "决定节点只提供重新选择的时机，不自动新增制度、权力、履约或和解。",
    ]
    value["initial_reason"] = f"双方首次围绕“{title}”核对事实、现实约束和当前选择。"
    value["initial_goal"] = "回应当前诉求，澄清分歧，并讨论一个可撤回、行动归属清楚的临时安排。"
    value["initial_live_questions"] = [
        "双方对哪项既有事实或责任理解不同",
        "当前有哪些可行且可撤回的选择",
        "等待公开记录期间各自愿意承担什么",
    ]
    value["initial_pause_when"] = "当前立场、待核验事实和再次联系依据已经明确，或一方明确要求暂停。"
    value["evidence_opening"] = (
        "预先说明的公开记录已经到了。我们只按它明示的内容重新判断，"
        "不能把未写明的动机、责任或完成结果补进去。"
    )
    value["evidence_goal"] = "依据公开记录调整判断，区分它确认的事实、仍不确定的解释和下一步选择。"
    value["evidence_live_questions"] = [
        "记录具体确认了什么",
        "哪些责任或动机仍不能由记录推出",
        "此前的临时安排是否需要调整",
    ]
    value["evidence_pause_when"] = "记录的有限含义、仍有分歧和下一次决定责任已经明确。"
    value["decision_opening"] = (
        f"现在到了重新决定“{title}”后续安排的节点。你可以继续、提出可核验条件、"
        "暂停或退出；我不会把其中任何一项说成已经发生。"
    )
    value["decision_goal"] = "基于现有证据作出有限决定，明确行动归属与核验方式，并允许拒绝或退出。"
    value["decision_live_questions"] = [
        "当前接受或拒绝哪项具体安排",
        "下一项行动由谁执行并由什么证据核验",
        "双方是继续、暂停还是退出当前关系安排",
    ]
    value["natural_endings"] = [
        "达成有限安排并保留待核验事项",
        "明确拒绝并说明可观察后果",
        "接受仍有分歧后暂停",
        "一方退出当前合作或关系安排",
    ]
    value["primary_states"] = [
        "emotion.anger", "emotion.anxiety", "motivation.resolve",
        "relationship.trust", "risk.goal_failure_risk",
    ]
    return value


def _expand_compact(card):
    _validate_compact(card)
    issue = card["title"]
    evidence = card["evidence_record"]
    decision = card["decision_record"]
    return {
        **card,
        "relevant_history": card["relevant_history"] + [
            f"双方已知后续会出现公开记录，但该记录只能证明其明示内容，不能自动解决{issue}。"
        ],
        "key_fact_boundaries": [
            f"当前已成立的是公开背景与三条相关历史，不把提案写成承诺。",
            f"公开证据只确认：{evidence}",
            "口头接受不等于行动完成，行为报告不等于可核验结果。",
            f"后续决定节点是：{decision}；节点到达不代表双方同意。",
        ],
        "meaningful_choices": [
            "核对双方对既有事实的不同解释及其证据。",
            "提出可撤回、可核验且行动归属清楚的临时安排。",
            "说明不能接受的边界，并允许对方拒绝或保留意见。",
            "等公开证据到达后调整判断，而不是预先宣布结果。",
            "在决定节点选择继续、暂停、升级程序或退出合作。",
        ],
        "initial_reason": f"双方需要在公开证据出现前讨论{issue}的事实边界与当前选择。",
        "initial_goal": "回应当前请求，区分事实、解释、提案和未履行事项。",
        "initial_live_questions": [
            "双方对哪项事实或责任理解不同",
            "当前有哪些可行且可逆的选择",
            "等待证据期间各自承担什么行动",
        ],
        "initial_pause_when": "当前请求已得到回应，待核验事实和等待理由清楚，可以合理暂停。",
        "evidence_opening": f"公开记录已经出来。它确认的是：{evidence} 我们需要据此重新讨论，不能把它说成争议已经解决。",
        "evidence_goal": "依据公开记录重新判断责任、选择和风险，不扩大证据含义。",
        "evidence_live_questions": [
            "记录确认了什么",
            "记录仍不能证明什么",
            "此前提案是否需要调整",
        ],
        "evidence_pause_when": "证据含义、仍有分歧及下一步责任已经明确，可以等待决定节点。",
        "decision_opening": f"现在到了预先说明的决定节点：{decision} 需要作出选择，但任何一方都可以拒绝、保留分歧或退出。",
        "decision_goal": "在现有证据下作出有边界的决定，并区分承诺与完成。",
        "decision_live_questions": [
            "当前接受或拒绝哪项具体安排",
            "谁负责下一项行动及如何核验",
            "关系或合作是否继续以及保留什么边界",
        ],
        "natural_endings": [
            "达成有限安排并留下待核验事项",
            "明确拒绝并说明后果",
            "接受分歧后暂停",
            "一方退出当前合作或关系安排",
        ],
        "primary_states": [
            "emotion.anger", "emotion.anxiety", "motivation.resolve",
            "relationship.trust", "risk.goal_failure_risk",
        ],
    }


def _validate_card(card):
    if not isinstance(card, dict) or set(card) != CARD_KEYS:
        raise ValueError(f"invalid card keys: {sorted(set(card) ^ CARD_KEYS)}")
    for key, count in (
        ("relevant_history", 4), ("key_fact_boundaries", 4),
        ("meaningful_choices", 5), ("initial_live_questions", 3),
        ("evidence_live_questions", 3), ("decision_live_questions", 3),
        ("natural_endings", 4),
    ):
        if not isinstance(card[key], list) or len(card[key]) != count:
            raise ValueError(f"{key} must contain {count} items")
    if not 1 <= card["evidence_after_days"] <= 7:
        raise ValueError("evidence_after_days outside 1..7")
    if not 1 <= card["decision_after_days"] <= 14:
        raise ValueError("decision_after_days outside 1..14")
    if not 4 <= len(card["primary_states"]) <= 6:
        raise ValueError("primary_states must contain 4..6 ids")
    list_keys = {
        "relevant_history", "key_fact_boundaries", "meaningful_choices",
        "initial_live_questions", "evidence_live_questions",
        "decision_live_questions", "natural_endings", "primary_states",
    }
    integer_keys = {"evidence_after_days", "decision_after_days"}
    scalar_keys = CARD_KEYS - list_keys - integer_keys
    if any(not isinstance(card[key], str) or not card[key].strip() for key in scalar_keys):
        raise ValueError("expanded scalar fields must be non-empty strings")


def _validate_cards(cards):
    if not isinstance(cards, list) or len(cards) != 5:
        raise ValueError("each family must contain exactly five cards")
    for card in cards:
        _validate_card(card)
    if len({card["title"] for card in cards}) != 5:
        raise ValueError("duplicate title in family")

def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def _generate_family(family, endpoint, retry_limit):
    target = CACHE / f"{family['family_id']}.json"
    if target.exists():
        value = json.loads(target.read_text())
        _validate_cards(value["cards"])
        return family["family_id"], "resumed", target
    cards = []
    attempts_used = []
    for slot in range(5):
        card_target = CACHE / "cards" / f"{family['family_id']}--{slot + 1}.json"
        if card_target.exists():
            cached_card = json.loads(card_target.read_text())
            _validate_card(cached_card["card"])
            cards.append(cached_card["card"])
            attempts_used.append(cached_card.get("attempt", 0))
            continue
        provider = build_provider({
            "provider": "local_vllm",
            "endpoint": f"{endpoint.rstrip('/')}/v1/chat/completions",
            "model": "Qwen/Qwen3-32B-AWQ",
            "timeout": 600,
            "max_tokens": 1200,
        })
        errors = []
        for attempt in range(1, retry_limit + 1):
            try:
                response_text = provider.complete(
                    [{"role": "user", "content": _prompt(family, slot)}],
                    temperature=0.55,
                    top_p=0.9,
                    seed=150000 + len(family["family_id"]) * 101 + slot * 17 + attempt,
                )
                compact_card = _parse_json_object(response_text)
                card = _normalize_runtime_card(_expand_compact(compact_card))
                _validate_card(card)
                _atomic_json(card_target, {
                    "format": "socialflux_scale150_design_card_v1",
                    "family_id": family["family_id"],
                    "slot": slot + 1,
                    "relationship_target": RELATION_TARGETS[slot],
                    "generation_model": "Qwen/Qwen3-32B-AWQ",
                    "attempt": attempt,
                    "compact_card": compact_card,
                    "card": card,
                })
                cards.append(card)
                attempts_used.append(attempt)
                break
            except Exception as exc:
                errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
        else:
            raise RuntimeError(
                f"{family['family_id']} card {slot + 1} exhausted: {' | '.join(errors)}"
            )
    seen_titles = set()
    for slot, card in enumerate(cards, start=1):
        title = card["title"]
        if title in seen_titles:
            title = f"{title}（{card['relationship_category']}）"
        if title in seen_titles:
            title = f"{title}-{slot}"
        card["title"] = title
        seen_titles.add(title)
    _validate_cards(cards)
    _atomic_json(target, {
        "format": "socialflux_scale150_design_family_v1",
        "family": family,
        "generation_model": "Qwen/Qwen3-32B-AWQ",
        "attempts_by_card": attempts_used,
        "cards": cards,
    })
    return family["family_id"], "generated", target

def _pool(pool_id, record):
    return {
        "event_pool_id": pool_id,
        "selection": "deterministic_by_trajectory_id",
        "outcomes": [{
            "outcome_id": "authored_public_record",
            "public_record": record,
            "causal_scope": "exogenous",
            "commitment_effect": "none",
            "state_delta": {},
            "dynamics_delta": {},
        }],
    }


def _segment(segment_id, reason, goal, questions, pause, cap, **extra):
    value = {
        "segment_id": segment_id,
        "reason": reason,
        "interaction_goal": goal,
        "live_questions": questions,
        "pause_when": pause,
        "min_turns": 1,
        "max_turns": cap,
        "allow_explicit_pause": True,
        "time_effect": {"policy": "none", "state_delta": {}, "dynamics_delta": {}},
    }
    value.update(extra)
    return value


def _source(family, index):
    if family["source_type"] == "narrative-derived":
        return {
            "type": "narrative-derived",
            "provenance_id": f"scale200-structural-{index:03d}-{family['family_id']}",
            "surface_text_policy": "original_surface_text",
            "redistribution_status": "transformed_structural_abstraction",
            "provenance_note": (
                f"仅借鉴《{family['source_work']}》的高层关系冲突空间；本项目角色、事实、"
                "时间节点、选择和全部对白均为改写。具体集数与时间戳待人工核实，未作相关声明。"
            ),
            "work_title": family["source_work"],
            "year": family["year"],
            "medium": family["medium"],
            "related_characters_or_plot_position": "high-level relational structure only; episode-level provenance pending verification",
        }
    return {
        "type": "synthetic-script",
        "provenance_id": f"scale200-original-{index:03d}-{family['family_id']}",
        "surface_text_policy": "original_surface_text",
        "redistribution_status": "original_synthetic_scenario",
        "provenance_note": "原创社会互动机制组合；没有使用可识别的具体作品角色、事件序列或对白。",
    }


def _generic_video_triggers(scenario_id):
    """Keep the canonical three-trigger contract aligned to the shared ontology."""
    return [
        {
            "trigger_id": "escalation_confrontation",
            "trigger_mode": "crossing",
            "conditions": {
                "emotion.anger": {"operator": ">=", "threshold": 8},
                "relationship.hostility": {"operator": ">=", "threshold": 7},
                "escalation_risk": {"operator": ">=", "threshold": 8},
            },
            "cooldown_turns": 3,
            "media_type": "video",
            "cue_template": "bounded_confrontation",
            "duration_seconds": 6,
            "media_asset_id": f"{scenario_id}--escalation_confrontation",
            "observable_expression": {
                "facial_expression": "表情收紧但不过度夸张",
                "gaze": "保持直接而克制的注视",
                "speech_style": "简短说明边界与当前分歧",
                "prosody": "句尾略微加重",
                "behavioral_cues": ["冲突升高后出现一次清晰外显变化"],
            },
            "priority": 2,
            "social_event": "bounded_confrontation",
            "spoken_response": "这件事不能继续含糊，我们先把边界说清楚。",
        },
        {
            "trigger_id": "anxious_withdrawal",
            "trigger_mode": "crossing",
            "conditions": {
                "emotion.anxiety": {"operator": ">=", "threshold": 8},
                "motivation.repair_intent": {"operator": "<=", "threshold": 2},
            },
            "cooldown_turns": 3,
            "media_type": "video",
            "cue_template": "anxious_withdrawal",
            "duration_seconds": 6,
            "media_asset_id": f"{scenario_id}--anxious_withdrawal",
            "observable_expression": {
                "facial_expression": "显出疲惫和戒备",
                "gaze": "短暂移开后重新看向对方",
                "speech_style": "句子变短，明确要求暂停",
                "prosody": "音量降低，停顿增加",
                "behavioral_cues": ["避免脸谱化情绪表演"],
            },
            "priority": 3,
            "social_event": "anxious_withdrawal",
            "spoken_response": "我现在很难继续谈下去，先停在这里。",
        },
        {
            "trigger_id": "repair_reengagement",
            "trigger_mode": "state_change",
            "conditions": {},
            "change_conditions": {
                "motivation.repair_intent": {"operator": ">=", "threshold": 2},
            },
            "cooldown_turns": 3,
            "media_type": "video",
            "cue_template": "repair_reengagement",
            "duration_seconds": 6,
            "media_asset_id": f"{scenario_id}--repair_reengagement",
            "observable_expression": {
                "facial_expression": "紧绷感略微缓和",
                "gaze": "重新稳定注视对方",
                "speech_style": "愿意核对具体事实和选择",
                "prosody": "语速放慢，表达更清晰",
                "behavioral_cues": ["先停顿再回应新的修复证据"],
            },
            "priority": 1,
            "social_event": "repair_reengagement",
            "spoken_response": "这项新信息我听到了，我们可以据此重新讨论。",
        },
    ]


def _build_scenario(index, family, card):
    base_index = ((index - 1) % 20) + 1
    base_path = SOURCE / f"scenario_{base_index:03d}" / f"scenario_{base_index:03d}.json"
    scenario = deepcopy(json.loads(base_path.read_text()))
    scenario_id = f"IA_PIPE_{index:03d}"
    scenario["scenario_id"] = scenario_id
    scenario["title"] = card["title"]
    scenario["mechanism"] = family["mechanism"]
    scenario["source"] = _source(family, index)
    scenario["background"] = card["background"]
    scenario["narrative_design"] = {
        "relationship_structure": card["relationship_category"],
        "power_structure": f"{card['evaluated_role']}与{card['environment_role']}掌握不同资源、证据或退出选择。",
        "goal_conflict": card["background"],
        "information_asymmetry": card["environment_hidden_intention"],
        "relevant_history": card["relevant_history"] + [
            "关键事实边界：" + "；".join(card["key_fact_boundaries"])
        ],
        "meaningful_choice_space": card["meaningful_choices"],
    }
    scenario["environment_agent"] = {
        "persona": {
            "name": card["environment_role"],
            "role": card["environment_role"],
            "patience": 0.5,
            "empathy": 0.5,
        },
        "explicit_goal": card["environment_goal"],
        "hidden_intention": card["environment_hidden_intention"],
    }
    scenario["evaluated_agent_role"] = {
        "character_id": "EVALUATED_AGENT",
        "name": "对话参与者",
        "explicit_goal": card["evaluated_goal"],
        "role": card["evaluated_role"],
    }
    scenario["selected_state_variables"] = {
        "emotion": ["anger", "anxiety", "hope"],
        "motivation": ["resolve", "repair_intent"],
        "relationship": ["trust", "hostility"],
        "dynamics": ["goal_failure_risk", "escalation_risk", "negotiation_open"],
    }
    scenario["target_state_ids"] = [
        "emotion.anger", "emotion.anxiety", "motivation.resolve",
        "relationship.trust", "risk.goal_failure_risk",
    ]
    scenario["initial_state"] = {
        "emotion": {"anger": 4, "anxiety": 5, "hope": 5},
        "motivation": {"resolve": 6, "repair_intent": 5},
        "relationship": {"trust": 5, "hostility": 3},
    }
    scenario["initial_dynamics"] = {
        "goal_failure_risk": 5, "escalation_risk": 4, "negotiation_open": 6,
    }
    environment_goal = card["environment_goal"].strip().rstrip("。；; ")
    scenario["opening_response"] = (
        f"我想先把“{card['title']}”说清楚。{environment_goal}。"
        f"{card['evidence_after_days']}天后的公开记录出来前，我们先明确各自现在能做什么。"
    )
    scenario["initialization_notes"] = {
        "rationale": {
            "state_selection": "使用既有通用社会互动 ontology；中等初值反映争议已出现但仍有多条自然路径。",
            "no_policy_effect": "S0/D0 不包含尚未生成的被评估 agent 行动效果，仍待 Gate 1 人工冻结。",
        },
        "trigger_reachability": ["本轮文本优先配置不预设多模态触发器。"],
    }
    scenario["observable_expression"] = {
        "default": {
            "facial_expression": "神情克制，随对话内容自然变化",
            "gaze": "保持符合当前关系的自然注视",
            "speech_style": "直接回应当前话语，不朗读规则或状态",
            "prosody": "语速和停顿随压力与犹豫变化",
            "behavioral_cues": ["必要时停顿、澄清或保留意见"],
        }
    }
    scenario["video_triggers"] = _generic_video_triggers(scenario_id)
    scenario["media_generation"] = {
        "stage": "text_first_pending_multimodal",
        "default_media_type": "text",
        "asset_status": "not_generated",
        "note": "Scale200 本轮先验证文本互动；通过 Gate 3 后再沿用既定多模态方案。",
    }
    scenario["max_turns"] = 20
    scenario["t3_delayed_horizon"] = 5
    scenario["sampling_plan"]["seed"] = 15000 + index
    evidence_pool_id = f"scale200_evidence_{index:03d}"
    scenario["longitudinal_design"] = {
        "format": "socialflux_longitudinal_v1",
        "time_unit": "day",
        "start_elapsed": 0,
        "segments": [
            _segment(
                "initial_interaction", card["initial_reason"], card["initial_goal"],
                card["initial_live_questions"], card["initial_pause_when"], 7,
            ),
            _segment(
                "authored_evidence_node", "预先说明的公开证据节点到达。",
                card["evidence_goal"], card["evidence_live_questions"],
                card["evidence_pause_when"], 7,
                advance_by=card["evidence_after_days"],
                public_time_record=(
                    f"距离上次互动过去{card['evidence_after_days']}天，预先安排的公开证据节点到达；"
                    "时间经过本身不证明任何承诺已经履行。"
                ),
                opening_response=card["evidence_opening"],
                event_pool_id=evidence_pool_id,
            ),
            _segment(
                "decision_or_review_node", card["decision_record"],
                card["decision_goal"], card["decision_live_questions"],
                "决定、拒绝、暂停或保留分歧的边界已经明确，可以自然结束。", 6,
                advance_by=card["decision_after_days"],
                public_time_record=(
                    f"又过去{card['decision_after_days']}天，"
                    f"{card['decision_record'].rstrip('。；; ')}；"
                    "节点到达不等于争议已经解决。"
                ),
                opening_response=card["decision_opening"],
            ),
        ],
        "event_pools": [_pool(evidence_pool_id, card["evidence_record"])],
    }
    scenario["construction_status"] = {
        "normalization": "scale200_v1_extension_card_and_state_alignment",
        "initial_state": "candidate_pending_human_freeze",
        "quality_gate": "pending_generation_and_semantic_review",
    }
    scenario["quality_gate"] = {key: "pending" for key in scenario["quality_gate"]}
    scenario["scenario_design_revision"] = {
        "version": "scale200_v1_extension_content_normalized",
        "design_family": family["family_id"],
        "design_model": "Qwen/Qwen3-32B-AWQ",
        "dialogue_policy": "authored evidence boundaries, not a turn script or forced outcome",
        "natural_endings": card["natural_endings"],
    }
    for trigger in scenario.get("video_triggers", []):
        trigger["media_asset_id"] = f"{scenario_id}--{trigger['trigger_id']}"
    validate_scenario(scenario)
    return scenario


def _row(scenario, family, index, inherited=False):
    segments = scenario.get("longitudinal_design", {}).get("segments", [])
    return {
        "scenario_id": scenario["scenario_id"],
        "title": scenario["title"],
        "relationship_category": scenario["narrative_design"]["relationship_structure"],
        "conflict_structure": scenario["mechanism"],
        "source_type": scenario["source"]["type"],
        "source_work": scenario["source"].get("work_title"),
        "source_verification": scenario["source"].get("provenance_note"),
        "primary_states": scenario["target_state_ids"],
        "time_organization": " → ".join(item["segment_id"] for item in segments),
        "task_potential": {
            "T1": "check_after_generation",
            "T2": "controlled_pair_design_only_not_two_independent_rollouts",
            "T3": "checkpoint_branch_potential; requires 5-10 subsequent turns",
            "T4": "online_natural_ending_candidate",
        },
        "design_family": "scale20_v2_inherited" if inherited else family["family_id"],
        "configuration_status": "schema_validated_pending_human_review",
        "generation_status": "not_generated_with_scale200_v1",
        "semantic_review_status": "not_reviewed",
        "authored_evidence_pool_count": len(scenario.get("longitudinal_design", {}).get("event_pools", [])),
        "ordinal": index,
    }


def _build_catalog():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    parent_matrix = json.loads(PARENT_MATRIX.read_text())
    rows = deepcopy(parent_matrix["scenarios"])
    seen_titles = {item["title"] for item in rows}
    for index in range(1, 151):
        source = PARENT / f"scenario_{index:03d}" / f"scenario_{index:03d}.json"
        target_dir = OUTPUT / f"scenario_{index:03d}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"scenario_{index:03d}.json"
        shutil.copyfile(source, target)
        write_document(target)

    index = 151
    for family in _extension_family_records():
        cached = json.loads((CACHE / f"{family['family_id']}.json").read_text())
        runtime_cards = [
            _normalize_runtime_card(deepcopy(item)) for item in cached["cards"]
        ]
        _validate_cards(runtime_cards)
        for cached_card in runtime_cards:
            card = deepcopy(cached_card)
            if card["title"] in seen_titles:
                card["title"] = (
                    f"{card['title']}｜{card['evaluated_role']}—{card['environment_role']}"
                )
            if card["title"] in seen_titles:
                card["title"] = f"{card['title']}（{index:03d}）"
            scenario = _build_scenario(index, family, card)
            seen_titles.add(scenario["title"])
            target_dir = OUTPUT / f"scenario_{index:03d}"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"scenario_{index:03d}.json"
            target.write_text(json.dumps(scenario, ensure_ascii=False, indent=2) + "\n")
            write_document(target)
            rows.append(_row(scenario, family, index))
            index += 1
    if index != 201:
        raise AssertionError(f"expected final index 201, got {index}")
    write_catalog(OUTPUT)
    source_counts = {}
    relation_counts = {}
    for row in rows:
        source_counts[row["source_type"]] = source_counts.get(row["source_type"], 0) + 1
        relation_counts[row["relationship_category"]] = relation_counts.get(row["relationship_category"], 0) + 1
    matrix = {
        "format": "socialflux_scale200_design_matrix_v1",
        "scenario_count": len(rows),
        "parent": "configs/scale150_v1",
        "design_contract": {
            "turn_target": "10-20 natural; short retained; 20 cap",
            "architecture": "structured appraisal LLM -> deterministic Python update -> response LLM",
            "evidence_policy": "authored public evidence nodes; no forced resolution or completion",
            "retention_policy": "retain every generated candidate and gate failure",
            "source_mix_target": "approximately 70% narrative-derived and 30% original",
            "scenario_content_revision": "v2: bounded readable evidence, non-prescriptive decision nodes, aligned opening and ontology",
        },
        "source_counts": source_counts,
        "relationship_counts": relation_counts,
        "scenarios": rows,
    }
    _atomic_json(OUTPUT.parent / "design_matrix.json", matrix)
    return matrix



def _write_rollout_configs():
    base = json.loads(
        (ROOT / "configs" / "scale20_v1" / "rollout.full20_v1.local.json").read_text()
    )
    rollout_root = OUTPUT.parent
    for shard in range(4):
        endpoint = f"http://127.0.0.1:{8301 + shard}/v1/chat/completions"
        config = deepcopy(base)
        config["pool_stage"] = "development"
        config["candidate_strategy"] = "single_first_pass"
        config["environment"]["provider"]["endpoint"] = endpoint
        config["environment"]["response_provider"]["endpoint"] = endpoint
        config["construction"]["provider"]["endpoint"] = endpoint
        policy = deepcopy(base["policies"][0])
        policy["policy_id"] = f"qwen3_32b_scale200_all_stages_shard_{shard + 1}"
        policy["provider"]["endpoint"] = endpoint
        policy["sampling"]["seed"] = 15201 + shard
        policy["environment_provider_override"]["endpoint"] = endpoint
        policy["environment_response_provider_override"]["endpoint"] = endpoint
        config["policies"] = [policy]
        config["scale200_shard"] = {
            "index": shard + 1,
            "count": 4,
            "scenario_rule": f"(ordinal - 1) % 4 == {shard}",
            "candidate_budget_per_scenario": 1,
            "retain_all_attempts": True,
        }
        _atomic_json(rollout_root / f"rollout.shard{shard + 1}.local.json", config)



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--endpoint", action="append",
        default=[], help="base endpoint, e.g. http://127.0.0.1:8301",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retry-limit", type=int, default=3)
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    endpoints = args.endpoint or [
        "http://127.0.0.1:8301", "http://127.0.0.1:8302",
        "http://127.0.0.1:8303", "http://127.0.0.1:8304",
    ]
    families = _extension_family_records()
    if not args.build_only:
        pending_families = []
        for family in families:
            target = CACHE / f"{family['family_id']}.json"
            if target.exists():
                print(f"inherited: {family['family_id']} -> {target}", flush=True)
            else:
                pending_families.append(family)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    _generate_family, family, endpoints[index % len(endpoints)],
                    args.retry_limit,
                ): family
                for index, family in enumerate(pending_families)
            }
            for future in as_completed(futures):
                family_id, status, target = future.result()
                print(f"{status}: {family_id} -> {target}", flush=True)
    matrix = _build_catalog()
    _write_rollout_configs()
    print(json.dumps({
        "scenario_count": matrix["scenario_count"],
        "source_counts": matrix["source_counts"],
        "output": str(OUTPUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
