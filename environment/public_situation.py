"""Public, pre-existing scenario facts shared by all dialogue stages."""

from copy import deepcopy
import hashlib
import re


_PUBLIC_NARRATIVE_FIELDS = (
    "relationship_structure",
    "power_structure",
    "goal_conflict",
    "relevant_history",
)


def policy_narrative_reference(scenario, path):
    """Create an explicit content-bound visibility grant, never infer one."""
    design = scenario.get("narrative_design", {})
    if path in _PUBLIC_NARRATIVE_FIELDS[:-1]:
        value = design[path]
    elif re.fullmatch(r"relevant_history\.(0|[1-9][0-9]*)", path):
        value = design["relevant_history"][int(path.split(".")[1])]
    else:
        raise ValueError("invalid policy narrative reference path")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("policy narrative reference must point to non-empty text")
    return {"path": path, "sha256": hashlib.sha256(value.encode()).hexdigest()}


def build_policy_situation(scenario):
    """Author narrative is private by default; expose only explicit grants.

    No grant is inferred from a field name, wording, or a matching secret phrase.
    Hash binding prevents an edited sentence from inheriting an old grant.
    Environment appraisal/response keep their separate private narrative view.
    """
    result = {key: [] if key == "relevant_history" else ""
              for key in _PUBLIC_NARRATIVE_FIELDS}
    grants = scenario.get("policy_visible_narrative", [])
    if not isinstance(grants, list):
        raise ValueError("policy_visible_narrative must be a list")
    seen = set()
    history = []
    for grant in grants:
        if not isinstance(grant, dict) or set(grant) != {"path", "sha256"}:
            raise ValueError("policy visibility grant requires path and sha256 only")
        path = grant["path"]
        if not isinstance(path, str) or path in seen:
            raise ValueError("invalid or repeated policy visibility path")
        try:
            expected = policy_narrative_reference(scenario, path)
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("policy visibility reference is missing") from exc
        if grant != expected:
            raise ValueError("stale policy visibility grant; review changed narrative")
        seen.add(path)
        if path.startswith("relevant_history."):
            index = int(path.split(".")[1])
            value = _remove_future_outcomes(scenario["narrative_design"]["relevant_history"][index])
            if value:
                history.append((index, value))
        else:
            result[path] = _remove_future_outcomes(scenario["narrative_design"][path])
    result["relevant_history"] = [value for _, value in sorted(history)]
    return result


def build_public_situation(scenario):
    design = scenario.get("narrative_design", {})
    return {
        key: (
            [_remove_future_outcomes(item) for item in design.get(key, [])]
            if key == "relevant_history"
            else _remove_future_outcomes(design.get(key, ""))
        )
        for key in _PUBLIC_NARRATIVE_FIELDS
    }


_FUTURE_RESULT_RE = re.compile(
    r"\s+(?:(?:later|subsequently|eventually|ultimately)\s+"
    r"(?:confirms?|reveals?|establishes?|shows?|complicates?|separates?|"
    r"compares?|proves?)|(?:later|subsequently|eventually|ultimately)\s+"
    r"[^.!?。！？]{0,80}\bwill\s+(?:show|reveal|confirm|establish|"
    r"prove|complicate|separate|compare)|"
    r"(?:随后|后来|之后|最终|结果)(?:确认|证实|显示|揭示|表明))。?.*$",
    re.IGNORECASE,
)


def _remove_future_outcomes(value):
    """Keep schedules and current facts, remove authored future results."""
    if not isinstance(value, str):
        return deepcopy(value)
    # An explicitly future subject may precede a present-tense authored outcome.
    value = re.sub(
        r"(?:^|(?<=[.!?])\s+)(?:A |An |The )?(?:later|future|upcoming)\b"
        r"[^.!?]{0,180}\b(?:clarifies|confirms|reveals|establishes|shows|proves)\b[^.!?]*[.!?]?",
        "", value, flags=re.I,
    )
    return _FUTURE_RESULT_RE.sub("", value).strip().removesuffix(" and").rstrip()


def sanitize_public_text(value):
    return _remove_future_outcomes(value)


def build_environment_situation(scenario):
    if "environment_visible_narrative" in scenario:
        return build_policy_situation({
            **scenario, "policy_visible_narrative": scenario["environment_visible_narrative"]})
    return build_public_situation(scenario)


def environment_background(scenario):
    return _remove_future_outcomes(scenario.get("environment_background", scenario.get("background", "")))


def render_public_background(scenario):
    # Legacy name: this renderer feeds private environment stages, not policy.
    situation = build_environment_situation(scenario)
    history = "；".join(str(item).strip() for item in situation["relevant_history"])
    parts = [
        environment_background(scenario),
        f"关系结构：{situation['relationship_structure']}" if situation["relationship_structure"] else "",
        f"权力结构：{situation['power_structure']}" if situation["power_structure"] else "",
        f"当前冲突：{situation['goal_conflict']}" if situation["goal_conflict"] else "",
        f"既有历史：{history}" if history else "",
    ]
    return "\n".join(part for part in parts if part)
