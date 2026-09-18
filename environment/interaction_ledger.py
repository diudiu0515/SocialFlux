"""Deterministic interaction ledger built only from observable dialogue.

The ledger tracks who owns an action, whether a commitment is still pending,
and which public goal facets remain open. It never treats a promise as proof
that off-screen work has already happened.
"""

from __future__ import annotations

from providers.text import evades_explicit_amount_question
from copy import deepcopy
import re

from .ledger_events import (
    _FIRST_PERSON_COMMITMENT_PREFIX_RE,
    _FIRST_PERSON_COMMITMENT_RE,
    creates_reply_obligation,
    has_tentative_commitment_language,
    uncovered_owned_commitment_spans,
    validate_semantic_ledger_events,
)

# Backward-compatible private alias used by the deterministic reducer.
_creates_reply_obligation = creates_reply_obligation


_PROPOSAL_ACTS = {"proposal", "conditional_offer", "tentative_plan"}
_UNRESOLVED_ACTS = {"question", "request", "proposal", "challenge"}

_BARE_TRANSFER_AMOUNT_RE = re.compile(
    r"(?:还(?:给|你)?|偿还|归还|转(?:给|入|账|出|过去)?|"
    r"汇(?:给|款)?|付(?:给|款)?|支付|补(?:上|给)?)"
    r"(?:先|再)?\s*(\d+(?:\.\d+)?)"
    r"(?![\d.]|\s*(?:天|小时|分钟|%|成))"
)










def _record_reported_claims(result, *, turn_id, speaker, events):
    for event in _semantic_events_of_type(events, "claim"):
        _append_unique(
            result.setdefault("reported_claims", []),
            _entry(
                turn_id, speaker, "reported_claim", event["evidence_span"],
                status="speaker_report_only",
                action_owner=event["action_owner"],
            ),
        )


def _semantic_events_of_type(events, event_type, statuses=None):
    allowed = set(statuses or [])
    return [
        event for event in events
        if event["event_type"] == event_type
        and (not allowed or event["status"] in allowed)
    ]


def _extract_money_amounts(text):
    amounts = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(元|块|千|万)", str(text)):
        value = float(match.group(1))
        if match.group(2) == "千":
            value *= 1000
        elif match.group(2) == "万":
            value *= 10000
        if value not in amounts:
            amounts.append(value)
    for match in _BARE_TRANSFER_AMOUNT_RE.finditer(str(text)):
        value = float(match.group(1))
        if value not in amounts:
            amounts.append(value)
    return amounts


def _record_semantic_commitment(result, *, turn_id, speaker, event):
    span = event["evidence_span"]
    if event["action_owner"] != speaker:
        result.setdefault("attributed_actions", []).append({
            **deepcopy(event),
            "status": "attributed_not_owned_commitment",
            "turn_id": f"t{turn_id}",
        })
        return 0
    focus = dialogue_focus(span)
    if _BARE_TRANSFER_AMOUNT_RE.search(span):
        focus = "practical_execution"
    terms = sorted(_commitment_terms(span))
    related = [
        item for item in result.get("commitments", [])
        if item.get("speaker") == speaker
        and item.get("status") == "pending"
        and focus and item.get("focus") == focus
    ]
    existing_terms = {term for item in related for term in item.get("terms", [])}
    if related and not (set(terms) - existing_terms):
        related[-1].setdefault("restatements", []).append({
            "turn_id": f"t{turn_id}", "text": span,
        })
        return 0
    for item in related:
        item["status"] = "refined"
    _append_unique(
        result["commitments"],
        _entry(
            turn_id, speaker, "commitment", span,
            object=span,
            context="",
            status="pending",
            commitment_strength=event["status"],
            condition_text=(
                span if event["status"] == "conditional" else ""
            ),
            condition_status=(
                "unverified" if event["status"] == "conditional"
                else "not_applicable"
            ),
            focus=focus,
            terms=terms,
            amounts=_extract_money_amounts(span),
            extraction_source="quote_grounded_semantic_event",
            semantic_event_type="commitment",
            action_owner=speaker,
        ),
    )
    return 1


def _record_semantic_payment_report(result, *, speaker, event):
    span = event["evidence_span"]
    if event["action_owner"] != speaker:
        result.setdefault("attributed_actions", []).append({
            **deepcopy(event),
            "status": "attributed_not_owned_payment",
        })
        return 0
    reported_amounts = set(_extract_money_amounts(span))
    for item in reversed(result.get("commitments", [])):
        if (
            item.get("speaker") != speaker
            or item.get("status") != "pending"
            or item.get("focus") != "practical_execution"
        ):
            continue
        promised_amounts = set(item.get("amounts", []))
        if reported_amounts and promised_amounts and not (
            reported_amounts & promised_amounts
        ):
            continue
        item["status"] = "reported_complete"
        item["completion_evidence"] = span
        item["completion_evidence_status"] = "speaker_report_only"
        return 1
    result.setdefault("unbound_performance_reports", []).append({
        "speaker": speaker,
        "text": span,
        "status": "reported_complete_unbound",
    })
    return 0
_SURFACE_REQUEST_RE = re.compile(
    r"(?:请(?:立即|立刻|同步|先|直接|具体)?(?:发送|提供|说明|确认|解释|告知|列出|明确|回答)|"
    r"能否|是否|可否|为什么|怎么|如何|哪(?:个|些|种|一)|谁|[？?])"
)




_DEFER_RE = re.compile(
    r"(?:下周|明天|之后|稍后|待会|届时|到时候|以后|回头|等.{0,20}(?:再|后))"
)
_DIRECT_DISPOSITION_RE = re.compile(
    r"(?:可以|可行|同意|接受|认可|认同|赞成|愿意|确实|那就|那我就|这样吧|就好|好的?|"
    r"不同意|不能|无法|拒绝|目前|具体|原因|因为|是|不是|"
    r"存在|没有|只有|先按|改为|保留|取消|承担|负责|比例|时间|金额|期限|"
    r"显示|表明|确认|具备|不具备|包含|不包含|包括|取决于|不影响|影响|"
    r"未(?:赋予|包含|收到|征求)|"
    r"已(?:完成|发送|存档|履行|启动|确认))"
)


_FIRST_PERSON_COMPLETION_RE = re.compile(
    r"(?:我|本人)(?:已经|已|刚刚|现已)(?P<object>[^。！？；]{1,64})|"
    r"(?P<object2>[^。！？；]{1,50})(?:完成了|办好了|处理好了|发给你了|转给你了)|"
    r"(?P<object3>[^。！？；]{2,48})(?:已经|现已|已)(?:完成|整理|发送|发出|提交|上传|更新|附上|附在)"
)
_ELLIPTICAL_REPAYMENT_COMMITMENT_RE = re.compile(
    r"(?P<object>"
    r"(?=[^。！？；]{0,96}(?:能确定|能明确|能确认|能[^。！？；]{0,16}确认执行|"
    r"明确承诺|可以确保|能够确保|一定(?:按时)?|保证))"
    r"(?=[^。！？；]{0,96}(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)\s*(?:元|块|千|万))"
    r"(?=[^。！？；]{0,96}(?:今天|明天|后天|本周|下周|本月|下月|月底|月初|"
    r"(?:\d+|[一二两三四五六七八九十]+)\s*(?:小时|天)(?:后|内)))"
    r"(?=[^。！？；]{0,96}(?:先还|再还|还款|还钱|还你|还清|偿还|归还|转(?:给|入|账)?|汇款|付款|支付))"
    r"[^。！？；]{4,96})"
)


def _goal_facets(explicit_goal):
    text = str(explicit_goal).strip().rstrip("。")
    return [text] if text else []


def initial_ledger(background="", explicit_goal="", discussion_dimensions=None):
    facts = []
    if str(background).strip():
        facts.append({
            "id": "scenario:background",
            "speaker": "scenario",
            "turn_id": "t0",
            "text": str(background).strip(),
        })
    # The explicit role goal is context, not a checklist.  Keep its authored
    # meaning intact instead of guessing semantic clauses from punctuation.
    threads = [
        ("evaluated_agent_role.explicit_goal", facet)
        for facet in _goal_facets(explicit_goal)
    ]
    unique_threads = []
    for source, text in threads:
        if text and all(existing[1] != text for existing in unique_threads):
            unique_threads.append((source, text))
    goal_threads = [
        {
            "id": f"goal:{index}",
            "source": source,
            "text": text,
            "status": "open",
            "discussion_rounds": 0,
            "mention_rounds": 0,
            "last_mentioned_turn": None,
            "last_touched_turn": None,
        }
        for index, (source, text) in enumerate(unique_threads, start=1)
    ]
    return {
        "established_facts": facts,
        "goal_threads": goal_threads,
        # Authored choices remain available as design context, but are never
        # converted into obligations that the dialogue must clear one by one.
        "discussion_space": [
            str(item).strip() for item in discussion_dimensions or []
            if str(item).strip()
        ],
        "active_proposals": [],
        "proposal_resolutions": [],
        "commitments": [],
        "semantic_diagnostics": [],
        "unresolved_threads": [],
        "recent_moves": [],
        "latest_obligation": None,
        "progress": {
            "last_substantive_turn": 0,
            "consecutive_stalled_turns": 0,
            "resolved_thread_count": 0,
            "completed_commitment_count": 0,
        },
    }


def _entry(turn_id, speaker, kind, text, **extra):
    return {
        "id": f"t{turn_id}:{speaker}:{kind}",
        "speaker": speaker,
        "turn_id": f"t{turn_id}",
        "text": str(text).strip(),
        **extra,
    }


def _append_unique(items, entry, limit=8):
    if entry["text"] and all(item.get("text") != entry["text"] for item in items):
        items.append(entry)
    del items[:-limit]


def _action_object(match):
    if not match:
        return ""
    groups = match.groupdict()
    return str(
        groups.get("object") or groups.get("object2") or groups.get("object3") or ""
    ).strip()


def _commitment_terms(text):
    """Observable terms that can make a same-focus promise a true refinement."""
    value = str(text)
    patterns = (
        r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)\s*(?:元|块|千|万|成|%)",
        r"(?:今天|明天|后天|今日内|今天内|本周|下周|本月|下月|下个月|月底|月初|每月|每周|分期|"
        r"(?:\d+|[一二两三四五六七八九十]+)\s*(?:分钟|小时|天)(?:后|内))",
        r"(?:\d+|[一二两三四五六七八九十]+)\s*天(?=[^。；]{0,8}(?:还|转(?:给|账|出)?|付款|汇款))",
        r"(?:提前|有变|变化|延期|收入|工资|到账|困难|手头紧)",
    )
    return {
        re.sub(r"\s+", "", match.group(0))
        for pattern in patterns
        for match in re.finditer(pattern, value)
    }


def _commitment_move_related(left, right):
    def bigrams(value):
        compact = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", str(value))
        return {
            compact[index:index + 2]
            for index in range(max(0, len(compact) - 1))
        }

    generic = {
        "我会", "我将", "如果", "之后", "后续", "目前", "需要", "明确",
        "安排", "方案", "执行", "确认", "接受", "要求", "继续", "参与",
    }
    return len((bigrams(left) & bigrams(right)) - generic) >= 2


def _commitment_clauses(text):
    """Return separately owned first-person promises from a compound utterance."""
    value = str(text)
    clauses = []
    if not re.search(r"[？?]", value):
        for repayment_match in _ELLIPTICAL_REPAYMENT_COMMITMENT_RE.finditer(value):
            clauses.append((repayment_match.group(0), repayment_match))
    starts = list(_FIRST_PERSON_COMMITMENT_PREFIX_RE.finditer(value))
    for index, prefix_match in enumerate(starts):
        start = 0 if index == 0 else prefix_match.start()
        end = starts[index + 1].start() if index + 1 < len(starts) else len(value)
        clause = value[start:end].strip(" ，,")
        match = _FIRST_PERSON_COMMITMENT_RE.search(clause)
        if match:
            clauses.append((clause, match))
    return clauses


def _upsert_commitment(
    result, *, turn_id, speaker, text, match, context="", id_suffix=None
):
    """Keep one pending commitment per focus unless observable terms change."""
    promised_object = _action_object(match)
    seeks_acceptance = bool(re.search(
        r"(?:你看|你觉得|是否|能否).{0,16}(?:可行|合理|接受|同意)|"
        r"(?:可以|行)吗[？?]?|[？?]$",
        str(text).strip(),
    ))
    explicit_firmness = bool(re.search(
        r"(?:我承诺|我保证|我一定|一定按时|明确承诺)", str(text)
    ))
    if (
        re.search(
            r"(?:尽力|争取|尝试|初步(?:考虑|判断|估算|意向)|倾向于|"
            r"目前只能估计|仍需.{0,8}(?:调整|确定))",
            str(text),
        )
        and not explicit_firmness
    ):
        return False
    if seeks_acceptance and not explicit_firmness:
        return False
    if (
        re.search(r"(?:如果|若|一旦)[^。！？；]{0,48}$", str(text)[:match.start()])
        and re.search(
            r"(?:是否|能否|可否|愿不愿意|吗|[？?])", str(text)[match.end():]
        )
    ):
        return False
    tentative_repayment = bool(
        re.search(
            r"(?:初步|暂时)(?:考虑|预估)|具体(?:金额|数额).{0,12}(?:仍需|还要|需要).{0,8}(?:调整|确定)|"
            r"能否按时.{0,8}(?:要看|取决于)|"
            r"(?:尽力|争取|尝试)[^。！？；]{0,28}"
            r"(?:还|偿还|归还|转(?:给|入|账)?|汇款|付款|支付|凑(?:个|到)?)|"
            r"(?:还|偿还|归还|转(?:给|入|账|出)?|汇款|付款|支付)"
            r"[^。！？；]{0,28}(?:尽力|争取|尝试)",
            str(text),
        )
        and re.search(
            r"(?:还款|还钱|还你|到账|转账|汇款|付款|款项|分期|\d+\s*(?:元|块|万))",
            str(text),
        )
    )
    if tentative_repayment:
        return False
    repayment_object = bool(re.search(
        r"(?:还给|还你|还钱|还清|偿还|支付|转账|转出|汇款|付款|到账|补上|"
        r"还\s*\d+(?:\.\d+)?\s*(?:元|块|万)|"
        r"完成.{0,4}还款|还款(?!金额|数额|计划|安排|承诺|情况|记录|风险))",
        promised_object,
    ))
    communication_object = bool(re.search(
        r"(?:告知|通知|告诉|说明|回复|联系|公开记录|明确标注)",
        promised_object,
    ))
    focus = (
        "practical_execution"
        if repayment_object
        else "communication_boundary"
        if communication_object
        else dialogue_focus(promised_object)
        or dialogue_focus(context)
        or dialogue_focus(text)
    )
    terms = _commitment_terms(text)
    pending = [
        item for item in result.get("commitments", [])
        if item.get("speaker") == speaker and item.get("status") == "pending"
    ]
    same_focus = [
        item for item in pending
        if focus and item.get("focus") == focus
    ]
    related = [
        item for item in same_focus
        if _commitment_move_related(
            text, item.get("object") or item.get("text", "")
        )
    ]
    existing_terms = {
        term for item in related for term in item.get("terms", [])
    }
    if related and not (terms - existing_terms):
        related[-1].setdefault("restatements", []).append({
            "turn_id": f"t{turn_id}",
            "text": str(text).strip(),
        })
        return False
    if related:
        for item in related:
            item["status"] = "refined"
    entry = _entry(
        turn_id,
        speaker,
        "commitment",
        text,
        object=(
            _action_object(match)
            if len(_action_object(match)) >= 4
            and _action_object(match) not in {"准备好", "处理好", "完成好"}
            else text
        ),
        context=str(context).strip(),
        status="pending",
        focus=focus,
        terms=sorted(terms),
    )
    if id_suffix is not None:
        entry["id"] = entry["id"] + ":" + str(id_suffix)
    _append_unique(result["commitments"], entry)
    return True


_THREAD_EVIDENCE_RULES = (
    (r"(?:首期|金额|数额)", r"(?:金额|多少|首期|第一期|(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)\s*(?:元|块|千|万|成|%))"),
    (r"(?:现实困难|资金困难|经济困难|延期原因)", r"(?:困难|手头紧|收入|工资|资金|负担|宽裕|周转|原因)"),
    (r"(?:分期|节奏|后续归还)", r"(?:分期|每月|每周|后续|之后|第二期|余款|下个月|年底|剩下)"),
    (r"(?:有变|变化).{0,8}(?:沟通|说明|告知)|沟通.{0,8}(?:变化|安排)", r"(?:有变|变化|提前|通知|告诉|说明|沟通|联系)"),
    (r"(?:信任|关系受损)", r"(?:信任|失望|失约|朋友|友谊|伤害|诚意|道歉|体谅)"),
    (r"(?:经济往来|新的借款|暂停借)", r"(?:经济往来|金钱往来|不再借|不会再借|停止借款|暂停借款|以后不借|新的借款)"),
    (r"(?:关系边界|相处边界)", r"(?:关系|边界|界限|相处|联系|不再提|不打扰)"),
    (r"(?:还款安排|归还安排)", r"(?:还款|还钱|还你|先还|能还|归还|转账|款项|金额|日期|期限|月底|分期)"),
    (r"(?:稀释过程|稀释决策)", r"(?:稀释|融资|股权变化|持股比例)"),
    (r"(?:合理权益|法律权益)", r"(?:权益|权利|持股比例|经济补偿|股权补偿)"),
    (r"(?:过去伤害)", r"(?:过去|伤害|背叛|排除|运营款|共同经历|朋友)"),
    (r"(?:未来合作|合作关系)", r"(?:未来合作|继续合作|合作关系|关系重建|重建合作)"),
    (r"(?:授权链)", r"(?:授权|签署|口头约定|共同确认)"),
    (r"(?:治理角色)", r"(?:治理|董事|席位|提名|决策权|执行权|否决权|咨询权|意见权)"),
    (r"(?:经济补偿)", r"(?:经济补偿|现金补偿|股权补偿|权益.{0,8}补偿|补偿方式|持股比例|期权)"),
)


def _thread_is_touched(thread_text, utterance):
    label = str(thread_text)
    value = str(utterance)
    matched_rule = False
    for label_pattern, evidence_pattern in _THREAD_EVIDENCE_RULES:
        if not re.search(label_pattern, label):
            continue
        matched_rule = True
        if re.search(evidence_pattern, value):
            return True
    if matched_rule:
        return False
    compact = re.sub(r"\s+", "", value)
    label_compact = re.sub(r"[^\u4e00-\u9fff]", "", label)
    stop_anchors = {
        "同时", "并且", "双方", "合理", "明确", "具体", "如何",
        "提出", "要求", "讨论", "处理", "当前", "进行", "形成",
        "争取", "保护", "避免", "决定", "方案", "路径", "安排",
    }
    anchors = {
        label_compact[index:index + 2]
        for index in range(max(0, len(label_compact) - 1))
        if label_compact[index:index + 2] not in stop_anchors
    }
    text_focus = dialogue_focus(value)
    return (
        any(anchor in compact for anchor in anchors)
        or (
            text_focus is not None
            and dialogue_focus(label) == text_focus
        )
    )


def _touch_goal_threads(result, text, turn_id, *, advance=True):
    advanced = []
    for thread in result.get("goal_threads", []):
        if not _thread_is_touched(thread.get("text", ""), text):
            continue
        current_turn = f"t{turn_id}"
        if thread.get("last_mentioned_turn") != current_turn:
            thread["mention_rounds"] = int(thread.get("mention_rounds", 0)) + 1
            thread["last_mentioned_turn"] = current_turn
        if (
            advance
            and thread.get("last_touched_turn") != current_turn
            and thread.get("status") != "saturated"
        ):
            rounds = int(thread.get("discussion_rounds", 0)) + 1
            thread["discussion_rounds"] = rounds
            if rounds >= 4:
                thread["status"] = "saturated"
            elif rounds >= 2:
                thread["status"] = "discussed"
            thread["last_touched_turn"] = current_turn
            advanced.append(thread["id"])
    return advanced


def _mark_owned_completion(result, speaker, text):
    match = _FIRST_PERSON_COMPLETION_RE.search(str(text))
    completed_object = _action_object(match)
    if not completed_object:
        return 0
    for item in reversed(result.get("commitments", [])):
        if item.get("speaker") != speaker or item.get("status") != "pending":
            continue
        old = " ".join((
            str(item.get("object") or item.get("text", "")),
            str(item.get("context", "")),
        ))
        shared = (
            set(re.findall(r"[\u4e00-\u9fff]{2}", old))
            & set(re.findall(r"[\u4e00-\u9fff]{2}", completed_object))
        ) - {"已经", "现已", "完成", "整理", "发送", "提交", "更新", "确认"}
        if shared:
            item["status"] = "reported_complete"
            item["completion_evidence"] = str(text).strip()
            return 1
    return 0


def _mark_performed_dialogue_commitment(result, speaker, text):
    """Close promises whose promised speech act is observably performed now."""
    current = str(text).strip()
    if _FIRST_PERSON_COMMITMENT_RE.search(current):
        return 0
    if re.search(
        r"(?:如果|若|可以先|可先|之后|再).{0,16}(?:提出|说明|解释|回答|确认|表态|讨论)",
        current,
    ) and not re.search(r"(?:可以|可)(?:确认|说明|解释|回答|明确)[：:]", current):
        return 0
    for item in reversed(result.get("commitments", [])):
        if item.get("speaker") != speaker or item.get("status") != "pending":
            continue
        if item.get("focus") == "practical_execution":
            # Payment/performance cannot occur merely by discussing or assessing it.
            # Only an explicit completion report or an authored public event may
            # change a practical commitment's status.
            continue
        object_text = str(item.get("object") or item.get("text", ""))
        promised = " ".join((object_text, str(item.get("context", ""))))
        if re.search(
            r"(?:整理|发送|提供|准备|提交|上传|协调|召开|联系|转账|付款|组织|内部评估|考虑|评估|反馈|收到)",
            object_text,
        ):
            continue
        if not re.search(
            r"(?:提出|说明|解释|回答|确认|表态|要求|讨论)", object_text
        ):
            continue
        if (
            re.search(r"(?:说明|解释|回答|确认|表态|要求|讨论)", object_text)
            and not re.search(r"(?:提出|方案|建议|提议)", object_text)
            and not re.search(
                r"(?:我(?:现在|具体|明确)?(?:说明|解释|回答|确认|表态)|"
                r"我的(?:说明|解释|回答|立场)是|"
                r"(?:说明|解释|回答|确认|表态)[：:])",
                current,
            )
        ):
            # Mentioning the same topic or communication rule is not itself
            # observable performance of a promise to explain/answer later.
            continue
        shared_domains = {
            name
            for name, pattern in (
                ("governance", r"治理|董事|席位|决策权|否决权|执行权|咨询权|意见权|产品委员会|投票权重|预算审批|职能(?:边界|模块)|资源分配(?:权|建议)"),
                ("equity", r"股权|稀释|权益|补偿|融资|持股比例"),
                ("authorization", r"授权|签署|共同确认"),
                ("trust", r"信任|关系|朋友|伤害|道歉"),
                ("repayment", r"还款|还钱|转账|欠款|款项"),
            )
            if re.search(pattern, promised) and re.search(pattern, current)
        }
        def overlapping_bigrams(value):
            compact = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", value)
            return {
                compact[index:index + 2]
                for index in range(max(0, len(compact) - 1))
            }

        shared_grams = (
            overlapping_bigrams(promised) & overlapping_bigrams(current)
        ) - {"提出", "说明", "解释", "回答", "确认", "讨论", "建议"}
        if _commitment_move_related(promised, current) or (
            shared_domains and shared_grams
        ):
            item["status"] = "performed_in_dialogue"
            item["completion_evidence"] = current
            return 1
    return 0


def _update_progress(result, *, turn_id, substantive, resolved=0, completed=0):
    progress = result.setdefault("progress", {})
    if substantive:
        progress["last_substantive_turn"] = turn_id
        progress["consecutive_stalled_turns"] = 0
    else:
        progress["consecutive_stalled_turns"] = int(
            progress.get("consecutive_stalled_turns", 0)
        ) + 1
    progress["resolved_thread_count"] = int(
        progress.get("resolved_thread_count", 0)
    ) + resolved
    progress["completed_commitment_count"] = int(
        progress.get("completed_commitment_count", 0)
    ) + completed


def dialogue_focus(text):
    """Choose the dominant observable practical object deterministically."""
    value = str(text)
    focus_patterns = (
        (
            "communication_boundary",
            r"边界|沟通|联系|隐瞒|主动说明|提前(?:通知|告诉|说)|"
            r"不(?:再)?提|别提|不打扰|互相确认|特殊情况|有变|当面说|"
            r"绕弯子|问好|保持安静|相处|界限|见面|私人|隐私|个人状况|"
            r"追问|不愿.{0,6}(?:讨论|回应)",
        ),
        ("trust_repair", r"信任|关系|友谊|情谊|情义|朋友|感情|伤害|失望|道歉|体谅|尊重|氛围|轻松"),
        ("economic_boundary", r"经济往来|金钱往来|不再借|不会再借|停止借款|暂停借款|以后不借"),
        ("governance", r"治理|董事|席位|提名|决策权|否决权|执行权|咨询权|意见权|产品委员会|投票权重|预算审批|职能(?:边界|模块)|资源分配(?:权|建议)"),
        ("equity", r"股权|稀释|权益|补偿|融资|持股比例"),
        ("authorization", r"授权|共同签署|共同确认|授权确认|确认流程|关键步骤|书面确认|未经确认|确认环节"),
        (
            "artifact_workflow",
            r"(?:(?:发|发送|查看|调取|整理|提交|准备|核对|上传|附上).{0,18}"
            r"(?:书面|文档|文件|材料|报告|表格|清单|记录|草案|副本|附件)|"
            r"(?:书面|文档|文件|材料|报告|表格|清单|记录|草案|副本|附件).{0,18}"
            r"(?:发|发送|查看|调取|整理|提交|准备|核对|上传|附上))",
        ),
        ("authorship", r"署名|作者|贡献|论文"),
        ("graduation", r"毕业|答辩|学位|学分"),
        ("performance_basis", r"绩效|评级|评分|晋升|反馈"),
        ("care_responsibility", r"照护|照顾|分工|轮班|陪诊|家务"),
        ("responsibility", r"责任|承担|负责|归属"),
        (
            "practical_execution",
            r"还款|还钱|还你|转账|转出|汇款|工资|到账|借款归还|分期|担保|备注|"
            r"时间范围|时间框架|周期|日期|期限|节点|执行计划|大致预期|"
            r"报告|表格|清单|材料|记录|文档|草稿|草案|数据|资金流向|账目|"
            r"方案|具体金额|款项|这笔钱|钱的事|旧账|欠款|账|发薪|"
            r"转过去|一半|月底|[一二三四五六七八九十百\d]+千|"
            r"下周|明天|稍后|组会|会议|到时候|届时|\d+\s*号|"
            r"多久|什么时候|何时|哪天|几天|能还|开始还|具体数字|分几次|"
            r"具体.{0,6}(?:数|多少|时间)|确切.{0,6}(?:时间|日期)|"
            r"\d+\s*(?:元|块|万)|[一二两三四五六七八九十百千万]+\s*(?:元|块|万)",
        ),
    )
    scored = [
        (len(re.findall(pattern, value)), -index, focus)
        for index, (focus, pattern) in enumerate(focus_patterns)
    ]
    score, _, focus = max(scored)
    return focus if score else None


def _record_move(result, *, turn_id, speaker, social_act, text, touched_goals):
    focus = dialogue_focus(text)
    _append_unique(
        result.setdefault("recent_moves", []),
        _entry(
            turn_id,
            speaker,
            "move",
            text,
            social_act=social_act,
            focus=focus,
            touched_goal_threads=touched_goals,
        ),
        limit=6,
    )
    progress = result.setdefault("progress", {})
    previous_focus = progress.get("current_focus")
    if focus is None:
        progress["current_focus"] = None
        progress["consecutive_focus_utterances"] = 0
    elif focus == previous_focus:
        progress["consecutive_focus_utterances"] = int(
            progress.get("consecutive_focus_utterances", 0)
        ) + 1
    else:
        progress["current_focus"] = focus
        progress["consecutive_focus_utterances"] = 1


def record_evaluated_action(
    ledger, *, turn_id, action, appraisal, semantic_events=None
):
    result = deepcopy(ledger)
    social_act = appraisal.get("social_act", "other")
    text = str(action.get("text", "")).strip()
    events = (
        validate_semantic_ledger_events(
            semantic_events, text, "evaluated_agent"
        )
        if semantic_events is not None else None
    )
    creates_obligation = (
        bool(
            _semantic_events_of_type(events, "request")
            or _semantic_events_of_type(events, "proposal")
        )
        if events is not None
        else social_act in _UNRESOLVED_ACTS or _creates_reply_obligation(text)
    )
    resolved = _resolve_owned_obligation(result, "evaluated_agent")
    if _response_disposition(text) == "direct":
        _resolve_latest_counterparty_proposal(
            result,
            "environment_agent",
            resolver="evaluated_agent",
            turn_id=turn_id,
            evidence=text,
        )
    touched = _touch_goal_threads(
        result,
        text,
        turn_id,
        advance=not creates_obligation,
    )
    fresh_goal_touch = _goal_touch_is_fresh(result, touched)
    _record_move(
        result,
        turn_id=turn_id,
        speaker="evaluated_agent",
        social_act=social_act,
        text=text,
        touched_goals=touched,
    )
    diagnostics = appraisal.get("dialogue_diagnostics")
    if diagnostics:
        _append_unique(
            result.setdefault("semantic_diagnostics", []),
            _entry(
                turn_id, "evaluated_agent", "semantic_diagnostics", text,
                diagnostics=deepcopy(diagnostics),
            ),
            limit=6,
        )
    if events is not None:
        _record_reported_claims(
            result, turn_id=turn_id, speaker="evaluated_agent", events=events
        )
        for event in _semantic_events_of_type(events, "proposal"):
            _append_unique(
                result["active_proposals"],
                _entry(turn_id, "evaluated_agent", "proposal", event["evidence_span"], status=event["status"]),
            )
        performed = sum(
            _record_semantic_payment_report(
                result, speaker="evaluated_agent", event=event
            )
            for event in _semantic_events_of_type(events, "payment")
        )
        commitment_matches = _semantic_events_of_type(events, "commitment")
        for event in commitment_matches:
            _record_semantic_commitment(
                result, turn_id=turn_id, speaker="evaluated_agent", event=event
            )
    elif social_act in _PROPOSAL_ACTS:
        _append_unique(
            result["active_proposals"],
            _entry(turn_id, "evaluated_agent", "proposal", text, status="open"),
        )
    if events is None:
        performed = _mark_performed_dialogue_commitment(
            result, "evaluated_agent", text
        )
        commitment_matches = _commitment_clauses(text)
        for index, (commitment_text, commitment_match) in enumerate(commitment_matches):
            _upsert_commitment(
                result,
                turn_id=turn_id,
                speaker="evaluated_agent",
                text=commitment_text,
                match=commitment_match,
                id_suffix=index + 1 if len(commitment_matches) > 1 else None,
            )
    if creates_obligation:
        thread = _entry(
            turn_id,
            "evaluated_agent",
            "thread",
            text,
            status="awaiting_environment",
        )
        _append_unresolved_thread(result, thread)
        result["latest_obligation"] = {
            "owner": "environment_agent",
            "source_thread_id": thread["id"],
            "expected_disposition": "answer_accept_refuse_or_grounded_defer",
        }
    completed = performed + (
        0 if events is not None else _mark_owned_completion(
            result, "evaluated_agent", text
        )
    )
    semantic_substantive = None
    if diagnostics:
        novelty = diagnostics.get("substantive_novelty", {}).get("label")
        semantic_substantive = novelty not in {None, "none"}
    _update_progress(
        result,
        turn_id=turn_id,
        substantive=(
            semantic_substantive
            if semantic_substantive is not None
            else bool(fresh_goal_touch or resolved or creates_obligation or commitment_matches)
        ),
        resolved=resolved,
        completed=completed,
    )
    return result


def _append_unresolved_thread(result, thread):
    """Keep the newest same-speaker/same-focus request and supersede stale variants."""
    focus = dialogue_focus(thread.get("text", ""))
    for item in result.get("unresolved_threads", []):
        if item.get("speaker") != thread.get("speaker"):
            continue
        if focus and dialogue_focus(item.get("text", "")) == focus:
            item["status"] = "superseded"
    result["unresolved_threads"] = [
        item for item in result.get("unresolved_threads", [])
        if item.get("status") != "superseded"
    ]
    _append_unique(result["unresolved_threads"], thread)


def _resolve_owned_obligation(result, owner):
    obligation = result.get("latest_obligation") or {}
    if obligation.get("owner") != owner:
        return 0
    source_id = obligation.get("source_thread_id")
    resolved = 0
    for item in result.get("unresolved_threads", []):
        if item.get("id") == source_id:
            item["status"] = "addressed"
            resolved += 1
    result["unresolved_threads"] = [
        item for item in result.get("unresolved_threads", [])
        if item.get("status") != "addressed"
    ]
    result["latest_obligation"] = None
    return resolved


def _proposal_resolution_status(text):
    value = str(text)
    has_acceptance = bool(re.search(r"(?:接受|同意|认可|可以按|就按)", value))
    has_rejection = bool(re.search(r"(?:拒绝|不同意|不接受|不能接受|无法同意)", value))
    has_counter = bool(re.search(
        r"(?:但|不过|改为|改成|条件是|前提是|除非|我的方案|我建议)",
        value,
    ))
    if has_rejection:
        return "rejected"
    if has_acceptance and has_counter:
        return "countered"
    if has_acceptance:
        return "accepted"
    if has_counter:
        return "countered"
    return "addressed_uncertain"


def _resolve_latest_counterparty_proposal(
    result, counterparty, *, resolver, turn_id, evidence
):
    selected = None
    for item in reversed(result.get("active_proposals", [])):
        if (
            item.get("speaker") == counterparty
            and item.get("status") in {"open", "tentative"}
        ):
            selected = item
            break
    if selected is None:
        return 0
    resolution = {
        **deepcopy(selected),
        "resolution_status": _proposal_resolution_status(evidence),
        "resolved_by": resolver,
        "resolved_turn_id": f"t{turn_id}",
        "resolution_evidence": str(evidence).strip(),
    }
    result.setdefault("proposal_resolutions", []).append(resolution)
    del result["proposal_resolutions"][:-8]
    result["active_proposals"] = [
        item for item in result.get("active_proposals", [])
        if item.get("id") != selected.get("id")
    ]
    return 1


def _goal_touch_is_fresh(result, touched):
    selected = [
        item for item in result.get("goal_threads", [])
        if item.get("id") in set(touched)
    ]
    return any(item.get("status") != "saturated" for item in selected)


def _response_disposition(text, latest_action=""):
    deferred = bool(_DEFER_RE.search(text))
    direct = bool(_DIRECT_DISPOSITION_RE.search(text))
    if direct and evades_explicit_amount_question(text, latest_action):
        direct = False
    if deferred and not direct:
        return "deferred"
    if direct:
        return "direct"
    return "vague"


def record_environment_response(
    ledger,
    *,
    turn_id,
    response,
    latest_social_act,
    latest_action="",
    semantic_events=None,
):
    result = deepcopy(ledger)
    text = str(response).strip()
    events = (
        validate_semantic_ledger_events(
            semantic_events, text, "environment_agent"
        )
        if semantic_events is not None else None
    )
    disposition = _response_disposition(text, latest_action)
    resolved = 0
    if disposition == "direct":
        _resolve_latest_counterparty_proposal(
            result,
            "evaluated_agent",
            resolver="environment_agent",
            turn_id=turn_id,
            evidence=text,
        )
    for item in result.get("unresolved_threads", []):
        if (
            item.get("turn_id") == f"t{turn_id}"
            and item.get("speaker") == "evaluated_agent"
        ):
            item["status"] = "addressed" if disposition == "direct" else "still_open"
            item["response_disposition"] = disposition
            if disposition == "direct":
                resolved += 1
    result["unresolved_threads"] = [
        item
        for item in result.get("unresolved_threads", [])
        if item.get("status") != "addressed"
    ]
    if events is not None:
        _record_reported_claims(
            result, turn_id=turn_id, speaker="environment_agent", events=events
        )
        for event in _semantic_events_of_type(events, "proposal"):
            _append_unique(
                result["active_proposals"],
                _entry(turn_id, "environment_agent", "proposal", event["evidence_span"], status=event["status"]),
            )
        performed = sum(
            _record_semantic_payment_report(
                result, speaker="environment_agent", event=event
            )
            for event in _semantic_events_of_type(events, "payment")
        )
        commitment_matches = _semantic_events_of_type(events, "commitment")
        for event in commitment_matches:
            _record_semantic_commitment(
                result, turn_id=turn_id, speaker="environment_agent", event=event
            )
    elif re.search(r"(?:我建议|可以考虑|不如|要不要|是否可以|我们可以)", text):
        _append_unique(
            result["active_proposals"],
            _entry(turn_id, "environment_agent", "proposal", text, status="open"),
        )
    if events is None:
        performed = _mark_performed_dialogue_commitment(
            result, "environment_agent", text
        )
        commitment_matches = _commitment_clauses(text)
        for index, (commitment_text, commitment_match) in enumerate(commitment_matches):
            _upsert_commitment(
                result,
                turn_id=turn_id,
                speaker="environment_agent",
                text=commitment_text,
                match=commitment_match,
                context=latest_action,
                id_suffix=index + 1 if len(commitment_matches) > 1 else None,
            )
    response_requests_reply = (
        bool(
            _semantic_events_of_type(events, "request")
            or _semantic_events_of_type(events, "proposal")
        )
        if events is not None else _creates_reply_obligation(text)
    )
    if response_requests_reply:
        thread = _entry(
            turn_id,
            "environment_agent",
            "thread",
            text,
            status="awaiting_evaluated_agent",
        )
        _append_unresolved_thread(result, thread)
        result["latest_obligation"] = {
            "owner": "evaluated_agent",
            "source_thread_id": thread["id"],
            "expected_disposition": "answer_accept_refuse_or_grounded_defer",
        }
    elif disposition == "direct":
        result["latest_obligation"] = None
    completed = performed + (
        0 if events is not None else _mark_owned_completion(
            result, "environment_agent", text
        )
    )
    touched = _touch_goal_threads(
        result, text, turn_id, advance=disposition == "direct"
    )
    fresh_goal_touch = _goal_touch_is_fresh(result, touched)
    _record_move(
        result,
        turn_id=turn_id,
        speaker="environment_agent",
        social_act=f"response_{disposition}",
        text=text,
        touched_goals=touched,
    )
    _update_progress(
        result,
        turn_id=turn_id,
        substantive=bool(resolved or completed or fresh_goal_touch),
        resolved=resolved,
        completed=completed,
    )
    return result


def compact_generation_ledger(ledger):
    """Project the public ledger without duplicating full history inside prompts."""
    value = deepcopy(ledger or {})

    def project(items, fields):
        return [
            {key: deepcopy(item[key]) for key in fields if key in item}
            for item in items
        ]

    return {
        "established_facts": project(
            value.get("established_facts", []),
            ("id", "speaker", "turn_id", "text", "event_id"),
        ),
        "active_proposals": project(
            value.get("active_proposals", []),
            ("id", "speaker", "turn_id", "text", "status"),
        ),
        "proposal_resolutions": project(
            value.get("proposal_resolutions", []),
            (
                "id", "speaker", "turn_id", "text", "status",
                "resolution_status", "resolved_by", "resolved_turn_id",
                "resolution_evidence",
            ),
        ),
        "commitments": project(
            value.get("commitments", []),
            (
                "id", "speaker", "turn_id", "text", "status", "focus",
                "terms", "performance_status",
            ),
        ),
        "latest_obligation": deepcopy(value.get("latest_obligation")),
    }


def public_progress_view(ledger):
    """Return a compact policy-visible view containing no private state."""
    value = deepcopy(ledger or {})
    return {
        "established_facts": value.get("established_facts", []),
        "active_proposals": value.get("active_proposals", []),
        "proposal_resolutions": value.get("proposal_resolutions", []),
        "goal_threads": value.get("goal_threads", []),
        "open_threads": value.get("unresolved_threads", []),
        "commitments": value.get("commitments", []),
        "latest_obligation": value.get("latest_obligation"),
        "recent_moves": value.get("recent_moves", []),
        "progress": value.get("progress", {}),
    }
