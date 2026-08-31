"""Versioned natural-language action normalization for the deterministic pipeline."""

from copy import deepcopy


ACTION_KEYWORDS = {
    "repair": (
        "修复", "解决", "合作", "讨论", "沟通", "理解", "妥协", "方案",
        "说清楚", "冷静", "一起", "核对", "协调", "补救",
    ),
    "escalate": (
        "申诉", "投诉", "举报", "正式程序", "追责", "追究", "曝光", "律师",
        "威胁", "后果", "上报", "纪律", "处罚", "起诉",
    ),
    "neutral": (
        "等待", "先听", "更多信息", "不确定", "暂时", "再决定", "不表态",
        "保持中立", "事实", "等等", "观察",
    ),
}


def normalize_action(action, scenario):
    """Return a canonical action while preserving the submitted natural-language text.

    Structured action IDs remain authoritative. When only text is supplied, the
    highest keyword score selects a configured action; ties and unknown text fall
    back to neutral (or the first configured action).
    """
    submitted = deepcopy(action) if isinstance(action, dict) else {"text": str(action)}
    text = str(submitted.get("text", ""))
    effects = scenario.get("action_effects", {})
    supplied_id = submitted.get("action_id")
    if supplied_id in effects:
        submitted["action_id"] = supplied_id
        submitted.setdefault("text", text)
        return submitted

    configured = set(effects)
    scores = {
        action_id: sum(text.lower().count(keyword.lower()) for keyword in keywords)
        for action_id, keywords in ACTION_KEYWORDS.items()
        if action_id in configured
    }
    if scores:
        best_score = max(scores.values())
        if best_score > 0:
            selected = next(action_id for action_id in ("repair", "neutral", "escalate")
                            if scores.get(action_id) == best_score)
        else:
            selected = "neutral" if "neutral" in configured else sorted(configured)[0]
    else:
        selected = "neutral" if "neutral" in configured else sorted(configured)[0]
    return {"action_id": selected, "text": text}
