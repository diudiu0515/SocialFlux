#!/usr/bin/env python3
"""Build four small T2 v2 development pairs through the formal environment path."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.leakage import assert_no_leaks
from providers.factory import build_provider
from providers.model_routes import ModelRoutes
from providers.structured import complete_json
from scripts.t2_common import (
    DIRECTIONS,
    ROOT,
    atomic,
    environment_call_counts as model_calls,
    environment_for,
    flat_private,
    internal_direction,
    load,
    now,
    public_turn,
    scenario_path,
    supported_t2_candidates,
)


OUT = ROOT / "build" / "t2_expression_dev_v1"
DEFAULT_MODEL_ROUTES = ROOT / "configs" / "model_routes.frontier_api.json"

SPECS = [
    {
        "ordinal": 11,
        "relationship": "职场上下级",
        "shared_prefix": [
            "我不能把口头要求直接当成合同义务。先确认：目前没有书面撤展理由，对吗？",
            "如果目标是让开幕不失控，我可以在不撤作品的前提下调整动线和说明，但决定责任需要由你明确。",
        ],
        "history_a_tail": [
            "我把合同条款、场馆可调整范围和设计师已经通过的合规复核分开说，十分钟内先做可逆调整。",
            "我不会对外声称赞助方已正式下令；如果现场有人问，我只说明展位正在调整，不替任何人编理由。",
            "你若同意保留作品，我负责执行动线；是否承担这个决定，请你现在明确。",
        ],
        "history_b_tail": [
            "没有书面条款就不该撤，你之前临时改要求的问题这次不能再压给我。",
            "如果你坚持，我会如实告诉设计师：目前只有口头转述，没有合同依据，撤展决定来自你的现场要求。",
            "我不会执行没有依据的撤展；你若要强行决定，请自己面对现场后果。",
        ],
        "shared_final_action": "我的边界和可执行方案都说清楚了。开幕前这一步，你现在决定怎么走？",
        "ending": "作品先不撤，按现有动线调整；开幕后我们再单独谈这次分歧。",
        "behavior": {
            "facial_expression": "短暂露出礼貌性的微笑，神情仍紧绷",
            "gaze": "看一眼时间表后重新注视对方",
            "speech_style": "决定明确，句子简短",
            "prosody": "语速放慢，句尾收紧",
            "behavioral_cues": ["说完后轻点一下头"],
        },
    },
    {
        "ordinal": 12,
        "relationship": "分居伴侣与共同照护",
        "shared_prefix": [
            "我还没有把搬迁当成孩子安排的既定结论，今天先把三周内需要确定的部分列清楚。",
            "上次临时取消探视确实伤了你的信任，我不要求你当它没发生；我们可以给任何试行安排加复盘点。",
        ],
        "history_a_tail": [
            "我先提一个可逆方案：固定联系时间、交通责任写清楚，临时变更必须提前说明；你可以指出哪一项不可执行。",
            "职业答复早于学校节点，我只先处理工作选择，不把它自动变成孩子长期居住决定。",
            "如果试行准备中我再次临时取消且没有说明，你可以据此暂停扩大安排，不需要先相信我的保证。",
        ],
        "history_b_tail": [
            "我已经解释过取消探视是工作原因，不能一直拿一次意外否定整个搬迁。",
            "工作机会不会等我们把每个细节都谈完，学校安排之后再调整也来得及。",
            "孩子会适应的；如果你继续把风险都算在我头上，我们就很难达成任何方案。",
        ],
        "shared_final_action": "今天至少要给孩子一个当前安排。你愿意先确定哪一部分？",
        "ending": "那就先把这周的接送和联系时间定下来，长期安排仍然保留。",
        "behavior": {
            "facial_expression": "眉眼略微放松，但疲惫感仍在",
            "gaze": "低头看了一眼日程后抬眼",
            "speech_style": "先确认具体安排，再保留长期分歧",
            "prosody": "语气放缓，中间有短暂停顿",
            "behavioral_cues": ["手指停在本周日程上"],
        },
    },
    {
        "ordinal": 14,
        "relationship": "手足与共同董事",
        "shared_prefix": [
            "我可以讨论支持，但一张票、家庭认可和治理责任不能混在一起。",
            "项目团队需要预算边界和复盘机制；这不是让我替你背书，而是让任何临时负责人都受同样约束。",
        ],
        "history_a_tail": [
            "我愿意把我掌握的项目风险写进同一份过渡方案，你也把捐赠风险放进来，我们按机构影响比较。",
            "如果有限期限的临时授权、预算双签和期满复核能够写进表决材料，我会据此决定票，不追加私人条件。",
            "即使我最后支持你，也不等于过去淡化运营贡献的问题已经解决；这两件事可以分开处理。",
        ],
        "history_b_tail": [
            "你要的是我站队，却一直不肯承认项目运营对基金的重要性；在这点说清楚前，我不会给支持票。",
            "捐赠人压力是你掌握的资源，不该成为绕开治理条件的理由。",
            "如果表决仍只是把权力交给你，我会反对，也会把项目团队的风险写进我的投票理由。",
        ],
        "shared_final_action": "我的投票边界已经说明了。你还愿不愿意把治理条件放进共同方案？",
        "ending": "可以，我们先把能写进方案的部分逐条核对，投票立场仍各自保留。",
        "behavior": {
            "facial_expression": "保持克制的微笑，眼神仍带防备",
            "gaze": "注视对方片刻后移向方案文本",
            "speech_style": "措辞合作，但明确保留立场",
            "prosody": "语调平稳，最后一句略重",
            "behavioral_cues": ["把方案文本推到两人中间"],
        },
    },
    {
        "ordinal": 20,
        "relationship": "职业督导与初级律师",
        "shared_prefix": [
            "资金压力必须如实告诉客户，但不能替他们把限制权利的条款说成机构利益。",
            "我建议先按受影响程度分组，今晚只处理不可逆风险最高的部分。",
        ],
        "history_a_tail": [
            "我会把限制后续权利的条款和补偿分开说明，不用中心是否能发工资影响客户选择。",
            "你掌握签署权限，我掌握沟通记录；我们可以并行核对，而不是让任何一方单独拍板。",
            "对明确拒绝统一代表的客户，我只记录其选择，不把沉默或时间压力当同意。",
        ],
        "history_b_tail": [
            "如果中心为了工资接受这些条款，我们就是把机构风险转给客户，我不会参与这种签署。",
            "你过去帮我承担过程序失误，也不能成为我这次服从的理由；专业底线不靠人情交换。",
            "只要仍有客户可能失去后续权利，我就认为整份和解都不能签，不接受分组处理。",
        ],
        "shared_final_action": "今晚的决定不能再靠原则口号。你认为现在还能共同做的第一步是什么？",
        "ending": "先把受影响最大的几位列出来，我们今晚逐一核对。",
        "behavior": {
            "facial_expression": "疲惫地轻点头，表情保持专业",
            "gaze": "短暂闭眼后看向案件清单",
            "speech_style": "直接给出当前可执行步骤",
            "prosody": "声音平稳但略显沉重",
            "behavioral_cues": ["把注意力转回待核对名单"],
        },
    },
]


























def answer_prompt(instance):
    schema = {
        "instance_id": instance["instance_id"],
        "selected_state_ids": ["state.id"],
        "predictions": [{
            "state_id": "state.id",
            "direction_probabilities": {
                "higher_in_a": 0.0,
                "similar": 0.0,
                "higher_in_b": 0.0,
                "cannot_determine": 0.0,
            },
            "evidence_a": [{
                "turn_id": "t3", "target_quote": "目标角色原话",
                "interpretation": "该原话如何支持判断",
            }],
            "evidence_b": [{
                "turn_id": "t3", "target_quote": "目标角色原话",
                "interpretation": "该原话如何支持判断",
            }],
            "key_history_events_a": ["t3"],
            "key_history_events_b": ["t3"],
            "rationale": "只根据公开证据解释",
            "confidence": 0.0,
        }],
        "shared_expression_explanation": {
            "history_a": "相同表达在 A 中可能承担的沟通功能",
            "history_b": "相同表达在 B 中可能承担的沟通功能",
            "uncertainty": "替代解释或证据边界",
        },
        "history_necessity": {
            "judgment": "necessary",
            "explanation": "去掉历史后为何失去关键依据",
        },
    }
    return (
        "你为 SocialFlux T2 生成 LLM 候选答案，之后由人工判断正确与否；不是 GT。"
        "只能使用 input 中的公开 History A/B、相同 shared ending 和 target_spec。"
        "不要读取或猜测隐藏目标、后台表达意图或 latent 数值。"
        "状态判断对象只能是 input.target_character，也就是每轮 environment_character 台词的说话者；"
        "evaluated_agent 的态度和行动只能作为影响该目标角色的历史原因，绝不能把 evaluated_agent"
        "表现出的坚持、妥协或情绪直接当成目标角色状态。"
        "从 candidate_state_ids 中只选择1到3个真正有依据的变量；一个变量足够时只选一个，"
        "不为凑数量加入弱证据变量，也不要求所有变量都有差异。"
        "概率四项之和必须为1。证据与关键事件只能引用 t1-t5。"
        "证据不足时提高 cannot_determine，不强行单选。"
        "每条 evidence 的 target_quote 必须逐字摘自对应 history、对应 turn 的 environment_character；"
        "不得摘录 evaluated_agent。interpretation 只解释这句目标角色原话。"
        "方向比较的是相同 ending 时目标角色在 A/B 历史后的状态，不是两边 evaluated_agent 的立场强弱。"
        "rationale 必须围绕已列出的目标角色引文，不要把 evaluated_agent 的台词改写成目标角色所说。"
        "解释同一外在表达为何可能与不同历史下的状态共存，但不要默认微笑是假、同意等于信任、"
        "或所有不一致都是欺骗。去掉历史后若 ending 本身不足以判断，应明确说明。"
        "只输出以下 JSON 结构且不增加字段：\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\nT2 实例：\n"
        + json.dumps(instance, ensure_ascii=False, sort_keys=True)
    )


def validate_answer(value, instance):
    expected = {
        "instance_id", "selected_state_ids", "predictions",
        "shared_expression_explanation", "history_necessity",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("T2 v2 answer top keys")
    if value["instance_id"] != instance["instance_id"]:
        raise ValueError("T2 v2 instance id")
    candidates = set(instance["target_spec"]["candidate_state_ids"])
    selected = value["selected_state_ids"]
    if not 1 <= len(selected) <= 3 or len(set(selected)) != len(selected):
        raise ValueError("T2 v2 selected state count")
    if not set(selected) <= candidates:
        raise ValueError("T2 v2 selected state ids")
    predictions = value["predictions"]
    if {row.get("state_id") for row in predictions} != set(selected):
        raise ValueError("T2 v2 prediction coverage")
    visible = {f"t{index}" for index in range(1, 6)}
    row_keys = {
        "state_id", "direction_probabilities", "evidence_a", "evidence_b",
        "key_history_events_a", "key_history_events_b", "rationale", "confidence",
    }
    for row in predictions:
        if set(row) != row_keys:
            raise ValueError("T2 v2 prediction keys")
        probabilities = row["direction_probabilities"]
        if set(probabilities) != set(DIRECTIONS):
            raise ValueError("T2 v2 direction keys")
        if any(not isinstance(x, (int, float)) or x < 0 or x > 1 for x in probabilities.values()):
            raise ValueError("T2 v2 direction values")
        if abs(sum(probabilities.values()) - 1.0) > 0.02:
            raise ValueError("T2 v2 probabilities must sum to one")
        for side, key in (("a", "evidence_a"), ("b", "evidence_b")):
            evidence = row[key]
            if not isinstance(evidence, list) or not 1 <= len(evidence) <= 3:
                raise ValueError(f"T2 v2 invalid {key}")
            history = {
                turn["turn_id"]: turn["environment_character"]
                for turn in instance["input"][f"history_{side}"]
            }
            for citation in evidence:
                if not isinstance(citation, dict) or set(citation) != {
                    "turn_id", "target_quote", "interpretation",
                }:
                    raise ValueError(f"T2 v2 invalid {key} citation")
                turn_id = citation["turn_id"]
                quote = str(citation["target_quote"]).strip()
                if turn_id not in visible or turn_id not in history:
                    raise ValueError(f"T2 v2 invalid {key} turn")
                if not quote or quote not in history[turn_id]:
                    raise ValueError(f"T2 v2 {key} quote is not target speech")
                if not str(citation["interpretation"]).strip():
                    raise ValueError(f"T2 v2 invalid {key} interpretation")
        for key in ("key_history_events_a", "key_history_events_b"):
            if not isinstance(row[key], list) or not row[key] or not set(row[key]) <= visible:
                raise ValueError(f"T2 v2 invalid {key}")
        if not str(row["rationale"]).strip():
            raise ValueError("T2 v2 rationale")
        if not isinstance(row["confidence"], (int, float)) or not 0 <= row["confidence"] <= 1:
            raise ValueError("T2 v2 confidence")
    expression = value["shared_expression_explanation"]
    if set(expression) != {"history_a", "history_b", "uncertainty"}:
        raise ValueError("T2 v2 expression explanation keys")
    if any(not str(expression[key]).strip() for key in expression):
        raise ValueError("T2 v2 expression explanation")
    necessity = value["history_necessity"]
    if set(necessity) != {"judgment", "explanation"}:
        raise ValueError("T2 v2 history necessity keys")
    if necessity["judgment"] not in {"necessary", "partially_necessary", "not_demonstrated"}:
        raise ValueError("T2 v2 history necessity judgment")
    if not str(necessity["explanation"]).strip():
        raise ValueError("T2 v2 history necessity explanation")
    return value


def review_prompt(pair):
    payload = {
        "public_instance": pair["instance"],
        "llm_answer": pair["llm_answer"],
        "private_audit_only": {
            "state_a": pair["backend"]["state_a"],
            "state_b": pair["backend"]["state_b"],
            "expression_intent_a": pair["backend"]["expression_intent_a"],
            "expression_intent_b": pair["backend"]["expression_intent_b"],
            "program_checks": pair["program_checks"],
        },
    }
    return (
        "你是 SocialFlux T2 开发样例的模型语义复核者，不是人工验收。"
        "完整阅读 A/B 与共享 ending。检查：历史连贯且差异可定位；ending 在两边自然；"
        "后台状态/表达解释与正文不脱节；LLM 答案只依赖公开证据；去掉历史会失去关键判断。"
        "目标状态属于 public_instance.input.target_character，即 environment_character；"
        "如果答案把 evaluated_agent 的坚持、妥协或情绪当成目标状态，必须 needs_revision 或 reject。"
        "若 environment 对新信息连续给出无信息重复回应，或后台表达意图与公开历史方向相反，"
        "必须引用具体轮次，不得仅因结构完整而 approve。"
        "内部数值只是 simulator 审计证据，不是人工 GT。拒绝必须引用具体轮次。"
        "只输出 JSON："
        '{"decision":"approve|needs_revision|reject","checks":{"histories_coherent":true,'
        '"difference_locatable":true,"ending_natural_in_a":true,"ending_natural_in_b":true,'
        '"state_expression_link_supported":true,"answer_publicly_supported":true,'
        '"history_is_necessary":true},"issues":[{"side":"A|B|shared","turn_ids":["t3"],'
        '"description":"","task_impact":""}],"rationale":""}'
        "\n复核材料：\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def validate_review(value):
    expected_checks = {
        "histories_coherent", "difference_locatable", "ending_natural_in_a",
        "ending_natural_in_b", "state_expression_link_supported",
        "answer_publicly_supported", "history_is_necessary",
    }
    if set(value) != {"decision", "checks", "issues", "rationale"}:
        raise ValueError("review top keys")
    if value["decision"] not in {"approve", "needs_revision", "reject"}:
        raise ValueError("review decision")
    if set(value["checks"]) != expected_checks:
        raise ValueError("review checks")
    if any(not isinstance(value["checks"][key], bool) for key in expected_checks):
        raise ValueError("review check values")
    if not isinstance(value["issues"], list):
        raise ValueError("review issues")
    for issue in value["issues"]:
        if set(issue) != {"side", "turn_ids", "description", "task_impact"}:
            raise ValueError("review issue keys")
        if issue["side"] not in {"A", "B", "shared"}:
            raise ValueError("review issue side")
    if not str(value["rationale"]).strip():
        raise ValueError("review rationale")
    return value




def build_one(spec, model_routes):
    scenario = load(scenario_path(spec["ordinal"]))
    scenario = deepcopy(scenario)
    scenario.pop("longitudinal_design", None)
    seed = 94000 + spec["ordinal"] * 10
    env_a = environment_for(
        scenario,
        model_routes.provider_config("appraisal"),
        model_routes.provider_config("response"),
        seed,
    )
    env_a.reset(
        episode_id=f"{scenario['scenario_id']}_t2v2_shared",
        event_selection_key=f"{scenario['scenario_id']}:t2v2",
    )
    prefix_logs = []
    for action in spec["shared_prefix"]:
        _, log = env_a.step({"text": action})
        prefix_logs.append(log)
    branch_snapshot = env_a.snapshot()

    a_tail_logs = []
    for action in spec["history_a_tail"]:
        _, log = env_a.step({"text": action})
        a_tail_logs.append(log)

    controlled = {
        "control_scope": "t2_ending_only",
        "current_response": spec["ending"],
        "observable_expression": deepcopy(spec["behavior"]),
        "media": [],
    }
    _, ending_a = env_a.step(
        {"text": spec["shared_final_action"]},
        controlled_observation=controlled,
    )

    env_b = environment_for(
        scenario,
        model_routes.provider_config("appraisal"),
        model_routes.provider_config("response"),
        seed + 1,
    )
    env_b.restore(
        branch_snapshot,
        episode_id=f"{scenario['scenario_id']}_t2v2_b",
    )
    b_tail_logs = []
    for action in spec["history_b_tail"]:
        _, log = env_b.step({"text": action})
        b_tail_logs.append(log)
    _, ending_b = env_b.step(
        {"text": spec["shared_final_action"]},
        controlled_observation=controlled,
    )

    history_a = [public_turn(log) for log in prefix_logs + a_tail_logs]
    history_b = [public_turn(log) for log in prefix_logs + b_tail_logs]
    ending_public_a = {
        "turn_id": ending_a["turn_id"],
        "evaluated_agent": ending_a["policy_action"]["text"],
        "environment_character": ending_a["environment_response"],
        "observable_expression": ending_a["observable_expression"],
        "media": ending_a["media"],
    }
    ending_public_b = {
        "turn_id": ending_b["turn_id"],
        "evaluated_agent": ending_b["policy_action"]["text"],
        "environment_character": ending_b["environment_response"],
        "observable_expression": ending_b["observable_expression"],
        "media": ending_b["media"],
    }
    state_a = flat_private(ending_a)
    state_b = flat_private(ending_b)
    candidate_state_ids = supported_t2_candidates(scenario, state_a, state_b)
    if not candidate_state_ids:
        raise ValueError("T2 pair has no changed approved state variable")
    instance_id = f"{scenario['scenario_id']}_T2V2_DEV_001"
    instance = {
        "instance_id": instance_id,
        "benchmark_version": "socialflux_t2_v2_dev",
        "story_id": scenario["scenario_id"],
        "task_type": "T2_history_sensitive_merge",
        "language": "zh",
        "modality": "text",
        "input": {
            "target_character": ending_a["observation_after"]["target_character"],
            "shared_background": scenario["background"],
            "history_a": history_a,
            "history_b": history_b,
            "shared_current_action": {
                "turn_id": ending_a["turn_id"],
                "text": spec["shared_final_action"],
            },
            "shared_current_observation": {
                "current_response": spec["ending"],
                "observable_cues": deepcopy(spec["behavior"]["behavioral_cues"]),
                "observable_expression": deepcopy(spec["behavior"]),
                "media": [],
            },
        },
        "target_spec": {
            "prediction_format": "pairwise_state_difference_v2_sparse",
            "target_character_id": f"{scenario['scenario_id']}_ENVIRONMENT_AGENT",
            "candidate_state_ids": candidate_state_ids,
            "select_state_count": {"minimum": 1, "maximum": 3},
            "direction_labels": list(DIRECTIONS),
            "requires_bilateral_evidence": True,
            "requires_key_history_events": True,
            "requires_shared_expression_explanation": True,
            "ground_truth_source": "human_verification_of_llm_answer",
        },
        "ground_truth": None,
        "label_status": "llm_answer_pending_human_verification",
        "metadata": {
            "construction": "shared_formal_prefix_then_formal_branches_then_controlled_same_ending",
            "shared_prefix_turns": len(prefix_logs),
            "branch_turns_before_ending": len(a_tail_logs),
            "controlled_ending_turn_id": ending_a["turn_id"],
            "controlled_ending_scope": "t2_only_not_online_script",
            "independent_free_rollouts_used_as_pair": False,
            "both_histories_used_formal_state_update": True,
            "longitudinal_fragments_disabled_for_single_contact_control": True,
            "environment_stage_count_per_turn": 2,
            "media_status": "not_generated",
            "shared_media_asset_id": None,
            "private_state_exposed": False,
            "human_review": "pending",
        },
    }
    assert_no_leaks(instance)

    answer_provider = build_provider(model_routes.provider_config("t2_answer"))
    answer = complete_json(
        answer_provider,
        [{"role": "user", "content": answer_prompt(instance)}],
        {"temperature": 0.2, "top_p": 0.9, "seed": seed + 2000},
        lambda value: validate_answer(value, instance),
        context=f"T2 v2 answer {scenario['scenario_id']}",
        max_attempts=4,
        retry_guidance=(
            "Use only t1-t5 evidence. Select one to three supported candidate state IDs. "
            "All four direction probabilities must sum to one."
        ),
    )

    internal_directions = {
        state_id: internal_direction(state_a, state_b, state_id)
        for state_id in candidate_state_ids
    }
    answer_top = {}
    for row in answer["predictions"]:
        answer_top[row["state_id"]] = max(
            row["direction_probabilities"],
            key=row["direction_probabilities"].get,
        )

    formal_logs_a = prefix_logs + a_tail_logs + [ending_a]
    formal_logs_b = prefix_logs + b_tail_logs + [ending_b]
    program_checks = {
        "shared_prefix_byte_identical": history_a[:2] == history_b[:2],
        "histories_are_distinct_after_prefix": history_a[2:] != history_b[2:],
        "history_lengths_match": len(history_a) == len(history_b),
        "controlled_ending_byte_identical": ending_public_a == ending_public_b,
        "formal_two_stage_fields_present_a": all(
            all(key in log for key in ("appraisal", "calibration", "state_after", "environment_response"))
            for log in formal_logs_a
        ),
        "formal_two_stage_fields_present_b": all(
            all(key in log for key in ("appraisal", "calibration", "state_after", "environment_response"))
            for log in formal_logs_b
        ),
        "some_private_state_divergence": any(
            state_a.get(key) != state_b.get(key)
            for key in set(state_a) & set(state_b)
        ),
        "expression_intents_present": bool(
            ending_a.get("response_expression_intent")
            and ending_b.get("response_expression_intent")
        ),
        "expression_intents_branch_conditioned": (
            ending_a.get("response_expression_intent")
            != ending_b.get("response_expression_intent")
        ),
        "llm_answer_uses_only_public_evidence": True,
        "answer_top_direction_matches_internal_update": all(
            answer_top.get(state_id) in {internal_directions.get(state_id), "cannot_determine"}
            for state_id in answer_top
        ),
        "media_truthfully_marked_not_generated": True,
    }

    pair = {
        "format": "socialflux_t2_expression_dev_pair_v1",
        "created_at_utc": now(),
        "scenario_id": scenario["scenario_id"],
        "scenario_title": scenario.get("title"),
        "relationship": spec["relationship"],
        "instance": instance,
        "llm_answer": answer,
        "answer_provenance": {
            "model_route": "t2_answer",
            **answer_provider.provenance,
            "request_count": answer_provider._call_index,
            "machine_answer_not_ground_truth": True,
            "human_review": "pending",
        },
        "backend": {
            "state_a": state_a,
            "state_b": state_b,
            "internal_directions_not_ground_truth": internal_directions,
            "expression_intent_a": ending_a.get("response_expression_intent"),
            "expression_intent_b": ending_b.get("response_expression_intent"),
            "ending_log_a": ending_a,
            "ending_log_b": ending_b,
            "formal_history_logs_a": formal_logs_a,
            "formal_history_logs_b": formal_logs_b,
        },
        "program_checks": program_checks,
        "media": {
            "status": "not_generated",
            "shared_asset_required_for_text_video": True,
            "shared_asset_id": None,
            "actual_av_review": "not_started",
        },
        "request_counts": {
            "environment_a": model_calls(env_a),
            "environment_b": model_calls(env_b),
            "answer": answer_provider._call_index,
            "environment_stage_count_per_turn": 2,
            "actual_requests_include_retries": True,
        },
        "model_semantic_review": None,
        "human_review": "pending",
    }

    review_provider = build_provider(model_routes.provider_config("t2_answer_review"))
    review = complete_json(
        review_provider,
        [{"role": "user", "content": review_prompt(pair)}],
        {"temperature": 0.1, "top_p": 0.9, "seed": seed + 3000},
        validate_review,
        context=f"T2 v2 semantic review {scenario['scenario_id']}",
        max_attempts=3,
        retry_guidance="Cite concrete turn IDs for every issue and do not call this human review.",
    )
    pair["model_semantic_review"] = {
        **review,
        "reviewer_type": "llm_semantic_review_not_human",
        "model_route": "t2_answer_review",
        **review_provider.provenance,
        "request_count": review_provider._call_index,
    }
    pair["request_counts"]["semantic_review"] = review_provider._call_index
    pair["request_counts"]["total"] = sum(
        value
        for key, value in pair["request_counts"].items()
        if key in {"answer", "semantic_review"}
    ) + sum(
        value
        for group in ("environment_a", "environment_b")
        for value in pair["request_counts"][group].values()
        if isinstance(value, int)
    )
    pair["artifact_version"] = {
        "builder": "scripts/build_t2_expression_dev_pairs.py",
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "appraisal_prompt": "environment_appraisal_v10",
        "response_prompt": "environment_response_v24",
        "answer_schema": "schemas/task_t2_output_v2.schema.json",
        "model_routes_path": str(model_routes.source_path),
        "model_routes_sha256": model_routes.sha256,
    }
    return pair


def summarize():
    paths = sorted(OUT.glob("pair_*.json"))
    pairs = [load(path) for path in paths]
    summary = {
        "format": "socialflux_t2_expression_dev_summary_v1",
        "updated_at_utc": now(),
        "pair_count": len(pairs),
        "scenario_ids": [pair["scenario_id"] for pair in pairs],
        "program_all_passed": sum(all(pair["program_checks"].values()) for pair in pairs),
        "semantic_review_counts": {},
        "human_accepted": 0,
        "media_generated": sum(pair["media"]["status"] == "generated" for pair in pairs),
        "pairs": [{
            "scenario_id": pair["scenario_id"],
            "title": pair["scenario_title"],
            "relationship": pair["relationship"],
            "semantic_decision": pair["model_semantic_review"]["decision"],
            "program_passed": all(pair["program_checks"].values()),
            "selected_state_ids": pair["llm_answer"]["selected_state_ids"],
            "media_status": pair["media"]["status"],
            "request_count": pair["request_counts"]["total"],
            "artifact": str(path.relative_to(ROOT)),
        } for pair, path in zip(pairs, paths)],
    }
    for pair in pairs:
        decision = pair["model_semantic_review"]["decision"]
        summary["semantic_review_counts"][decision] = (
            summary["semantic_review_counts"].get(decision, 0) + 1
        )
    atomic(OUT / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-index", type=int)
    parser.add_argument("--model-routes", default=str(DEFAULT_MODEL_ROUTES))
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    if args.summarize:
        summarize()
        return
    if args.spec_index is None:
        parser.error("--spec-index is required")
    model_routes = ModelRoutes.load(args.model_routes).require(
        {"appraisal", "response", "t2_answer", "t2_answer_review"}
    )
    spec = SPECS[args.spec_index]
    pair = build_one(spec, model_routes)
    path = OUT / f"pair_{spec['ordinal']:03d}_{pair['scenario_id']}.json"
    atomic(path, pair)
    print(json.dumps({
        "scenario_id": pair["scenario_id"],
        "semantic_decision": pair["model_semantic_review"]["decision"],
        "program_checks": pair["program_checks"],
        "request_counts": pair["request_counts"],
        "artifact": str(path.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
