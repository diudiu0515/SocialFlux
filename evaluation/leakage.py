"""Audit that public benchmark records do not contain private simulator fields."""

PRIVATE_KEYS = {
    "effects", "flags_set", "terminal_effects", "hidden_intention", "appraisal",
    "state_before", "state_after", "state_delta", "dynamics_before", "dynamics_after",
    "dynamics_delta", "raw_effect_estimates", "trait_modifiers", "internal_research_log",
}


def find_leaks(value, path=""):
    leaks = []
    if isinstance(value, dict):
        for key, item in value.items():
            current = f"{path}.{key}" if path else key
            if key in PRIVATE_KEYS:
                leaks.append(current)
            leaks.extend(find_leaks(item, current))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            leaks.extend(find_leaks(item, f"{path}[{index}]"))
    return leaks


def assert_no_leaks(record):
    leaks = find_leaks(record)
    if leaks:
        raise ValueError("private fields in public instance: " + ", ".join(leaks))
    return True
