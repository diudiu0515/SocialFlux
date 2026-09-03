"""Observable-history retrieval; full raw history remains authoritative."""

import json
import re

from prompts.loader import render_prompt


def _tokens(text):
    return set(re.findall(r"[\w\u4e00-\u9fff]+", str(text).lower()))


class MemoryModule:
    """Dependency-free observable retrieval used when no model retriever is configured."""

    def __init__(self, max_events=4):
        self.max_events = max_events

    def retrieve(self, history, current_action):
        action_text = current_action.get("text", "") if isinstance(current_action, dict) else current_action
        action_tokens = _tokens(action_text)
        scored = []
        for item in history:
            overlap = len(action_tokens & _tokens(item.get("text", "")))
            recency = item.get("turn_id", 0) / max(1, len(history))
            scored.append((overlap * 2 + recency, item.get("turn_id", 0), item))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        selected = [item for _, _, item in scored[: self.max_events]]
        selected.sort(key=lambda item: item.get("turn_id", 0))
        return {
            "relevant_turn_ids": [f"t{x['turn_id']}" for x in selected],
            "memory_summary": " ".join(
                f"{x.get('role', 'unknown')}: {x.get('text', '')}" for x in selected
            ),
            "important_unresolved_events": [],
        }


class ModelMemoryModule:
    def __init__(self, provider, max_events=4, sampling=None):
        self.provider = provider
        self.max_events = max_events
        self.sampling = dict(sampling or {})

    def retrieve(self, history, current_action):
        prompt = render_prompt("memory_retrieval_v2", {
            "history": history,
            "current_action": current_action,
            "max_events": self.max_events,
        })
        raw = self.provider.complete(
            [{"role": "user", "content": prompt}],
            **self.sampling,
        )
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("model memory module returned invalid JSON") from exc
        required = {"relevant_turn_ids", "memory_summary", "important_unresolved_events"}
        if set(result) != required:
            raise ValueError("model memory module returned an invalid memory object")
        available = {f"t{item['turn_id']}" for item in history}
        if not set(result["relevant_turn_ids"]) <= available:
            raise ValueError("memory module referenced unavailable history")
        return result
