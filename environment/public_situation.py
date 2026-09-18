"""Public, pre-existing scenario facts shared by all dialogue stages."""

from copy import deepcopy


_PUBLIC_NARRATIVE_FIELDS = (
    "relationship_structure",
    "power_structure",
    "goal_conflict",
    "relevant_history",
)


def build_public_situation(scenario):
    design = scenario.get("narrative_design", {})
    result = {
        key: deepcopy(design.get(key, [] if key == "relevant_history" else ""))
        for key in _PUBLIC_NARRATIVE_FIELDS
    }
    result["discussion_dimensions"] = deepcopy(
        design.get("meaningful_choice_space", [])
    )
    return result


def render_public_background(scenario):
    situation = build_public_situation(scenario)
    history = "；".join(str(item).strip() for item in situation["relevant_history"])
    parts = [
        str(scenario.get("background", "")).strip(),
        f"关系结构：{situation['relationship_structure']}" if situation["relationship_structure"] else "",
        f"权力结构：{situation['power_structure']}" if situation["power_structure"] else "",
        f"当前冲突：{situation['goal_conflict']}" if situation["goal_conflict"] else "",
        f"既有历史：{history}" if history else "",
    ]
    return "\n".join(part for part in parts if part)
