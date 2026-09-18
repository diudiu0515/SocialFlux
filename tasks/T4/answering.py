"""Generate a machine T4 judgment from a completed public trajectory."""

from __future__ import annotations

from evaluation.t4_evaluation import public_t4_judge_packet, validate_t4_judgment
from prompts.loader import render_prompt
from providers.structured import complete_json
from scripts.t2_common import call_count


def generate_judgment(provider, trajectory, scenario, seed, *, max_attempts=3):
    packet = public_t4_judge_packet(trajectory, scenario)
    valid_turn_ids = [turn["turn_id"] for turn in trajectory["turns"]]
    start = call_count(provider)
    judgment = complete_json(
        provider,
        [{"role": "user", "content": render_prompt("t4_judge_v2", packet)}],
        {"temperature": 0.1, "top_p": 0.9, "seed": seed},
        lambda value: validate_t4_judgment(value, valid_turn_ids),
        context=f"T4 judgment {trajectory['trajectory_id']}",
        max_attempts=max_attempts,
        retry_guidance=(
            "Use exactly the five dimensions. Cite only visible turn IDs and keep "
            "automatic human_validation_status set to not_human_validated."
        ),
    )
    return packet, judgment, call_count(provider) - start
