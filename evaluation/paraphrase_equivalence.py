"""Deterministic pre-screen for strict pragmatic paraphrase candidates."""

from __future__ import annotations

import re


_MARKER_GROUPS = {
    "urgency": (
        "立即", "立刻", "即刻", "马上", "这就", "赶紧", "尽快",
        "现在", "此刻", "right now", "immediately",
    ),
    "politeness": ("请", "麻烦", "劳驾", "谢谢", "能否", "可以吗", "please"),
    "pressure": ("必须", "务必", "只能", "不得", "否则", "没得商量", "must"),
    "condition": ("如果", "若", "只要", "除非", "否则", "if", "unless"),
    "commitment": ("承诺", "保证", "答应", "一定会", "我会", "我将", "promise"),
    "negation": ("不", "没", "无", "别", "未", "cannot", "not", "never"),
}


def _has_any(text, markers):
    lowered = str(text).lower()
    return any(marker.lower() in lowered for marker in markers)


def _semantic_numbers(text):
    # Ordered-list labels change formatting, not propositional numeric content.
    without_list_labels = re.sub(
        r"(?m)^\s*\d+[.)、]\s*", "", str(text)
    )
    return re.findall(r"\d+(?:\.\d+)?%?", without_list_labels)


def strict_paraphrase_constraints(text):
    """Expose the exact lexical invariants checked by the deterministic gate."""
    present = {
        name: list(markers)
        for name, markers in _MARKER_GROUPS.items()
        if _has_any(text, markers)
    }
    absent = [name for name, markers in _MARKER_GROUPS.items() if not _has_any(text, markers)]
    return {
        "required_marker_groups": present,
        "forbidden_marker_groups": absent,
        "semantic_numbers_exact": _semantic_numbers(text),
        "question_force": any(mark in str(text) for mark in ("?", "？")),
    }


def strict_paraphrase_precheck(original, paraphrase):
    reasons = []
    original_numbers = _semantic_numbers(original)
    paraphrase_numbers = _semantic_numbers(paraphrase)
    if original_numbers != paraphrase_numbers:
        reasons.append("numeric_content_changed")
    for name, markers in _MARKER_GROUPS.items():
        if _has_any(original, markers) != _has_any(paraphrase, markers):
            reasons.append(f"{name}_strength_changed")
    original_question = any(mark in str(original) for mark in ("?", "？"))
    paraphrase_question = any(mark in str(paraphrase) for mark in ("?", "？"))
    if original_question != paraphrase_question:
        reasons.append("question_force_changed")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "checked_dimensions": [
            "numeric_content", "urgency", "politeness", "pressure",
            "condition", "commitment", "negation", "question_force",
        ],
        "human_review_required": True,
    }
