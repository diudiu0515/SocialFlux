"""Build evidence context from the final action and strictly prior history."""

from copy import deepcopy
from providers.text import normalize_text


def turn_number(value):
    return int(str(value).removeprefix("t"))


def build_appraisal_context(*, history, turns, action, current_turn_id,
                            interaction_ledger=None, longitudinal_context=None):
    current = turn_number(current_turn_id)
    historical_messages = [deepcopy(item) for item in history or []
                           if turn_number(item["turn_id"]) < current]
    grouped = {}
    for item in historical_messages:
        number = turn_number(item["turn_id"])
        row = grouped.setdefault(number, {
            "turn_id": f"t{number}", "evaluated_agent_action": None,
            "environment_agent_response": None,
        })
        field = {"evaluated_agent": "evaluated_agent_action",
                 "environment_agent": "environment_agent_response"}.get(item.get("role"))
        if field:
            row[field] = str(item.get("text", ""))
    action_text = str(action["text"]).strip()
    duplicates = [{
        "historical_turn_id": f"t{turn_number(item['turn_id'])}",
        "historical_action_text": str(item.get("text", "")),
        "match_type": "normalized_surface_action",
    } for item in historical_messages
       if item.get("role") == "evaluated_agent"
       and normalize_text(item.get("text", "")) == normalize_text(action_text)]
    evidence_history = []
    for turn in turns or []:
        if turn_number(turn["turn_id"]) >= current:
            continue
        evidence_history.append({
            "turn_id": f"t{turn_number(turn['turn_id'])}",
            "evidence_judgments": deepcopy(turn.get("state_judgments", [])),
            "dynamics_judgments": deepcopy(turn.get("dynamics_judgments", [])),
            "prior_numeric_update": deepcopy(turn.get("numeric_state_delta", {})),
        })
    ledger = interaction_ledger or {}
    obligation = ledger.get("latest_obligation") or {}
    thread = next((item for item in ledger.get("unresolved_threads", [])
                   if item.get("id") == obligation.get("source_thread_id")
                   and obligation.get("owner") == "evaluated_agent"), None)
    latest_response = next((item for item in reversed(historical_messages)
                            if item.get("role") == "environment_agent"), None)
    return {
        "current_turn": {"turn_id": f"t{current}", "speaker": "evaluated_agent",
                         "action_text": action_text},
        "historical_turns": [grouped[key] for key in sorted(grouped)],
        "historical_messages": historical_messages,
        "latest_environment_utterance": deepcopy(latest_response),
        "latest_unanswered_question": str(thread.get("text", "")) if thread else "",
        "latest_unanswered_question_source": deepcopy(thread),
        "duplicate_evidence_matches": duplicates,
        "state_evidence_history": evidence_history,
        "repetition_rule": "Evidence already present in history can be repeated even if it never changed a number. Surface matches alone do not decide semantic repetition; judge the current act and its new consequences.",
    }


def refreshed_memory(memory, context):
    result = deepcopy(memory)
    result["duplicate_evidence_matches"] = deepcopy(context["duplicate_evidence_matches"])
    result["deterministic_surface_duplicate_ids"] = [
        item["historical_turn_id"] for item in context["duplicate_evidence_matches"]]
    return result


def semantic_context(context, action):
    """Fail before a model call on absent/stale context; keep deltas audit-only."""
    if not context or context.get("current_turn", {}).get("action_text") != str(action["text"]).strip():
        raise ValueError("missing or stale appraisal_context for final action")
    result = deepcopy(context)
    for item in result.get("state_evidence_history", []):
        item.pop("prior_numeric_update", None)
    return result
