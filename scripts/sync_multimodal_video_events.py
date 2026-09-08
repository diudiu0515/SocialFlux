#!/usr/bin/env python3
"""Synchronize canonical scenarios with multimodel.md's three-event contract."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.multimodal_video_profiles import THIRD_EVENTS, UTTERANCES
from scripts.scenario_docs import discover_scenario_paths

SCENARIOS = ROOT / "configs" / "scenarios"


def dump(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    changed = []
    for path in discover_scenario_paths(SCENARIOS):
        scenario = json.loads(path.read_text(encoding="utf-8"))
        scenario_id = scenario["scenario_id"]
        triggers = scenario.get("video_triggers", [])
        if not 2 <= len(triggers) <= 3:
            raise ValueError(f"{scenario_id}: expected two legacy or three synced events")

        if len(triggers) == 2:
            triggers.append(THIRD_EVENTS[scenario_id])
        elif triggers[2]["trigger_id"] != THIRD_EVENTS[scenario_id]["trigger_id"]:
            raise ValueError(f"{scenario_id}: unexpected third video event")
        else:
            triggers[2] = THIRD_EVENTS[scenario_id]

        for index, trigger in enumerate(triggers):
            trigger["priority"] = 1 if index == 2 else index + 2
            trigger["cooldown_turns"] = 3
            trigger["duration_seconds"] = 6
            trigger["social_event"] = trigger.get(
                "social_event", trigger.get("cue_template", trigger["trigger_id"])
            )
            try:
                trigger["spoken_response"] = UTTERANCES[scenario_id][trigger["trigger_id"]]
            except KeyError as exc:
                raise ValueError(f"missing public utterance for {scenario_id}/{trigger['trigger_id']}") from exc
            trigger["media_asset_id"] = None

        scenario["video_triggers"] = triggers
        scenario["media_generation"]["asset_status"] = "pending_regeneration"
        scenario["media_generation"]["provider"] = "BadToBest/EchoMimicV2"
        scenario["media_generation"]["profile"] = "multimodel_v2_audio_conditioned"
        dump(path, scenario)
        changed.append(scenario_id)

    print(json.dumps({"scenarios": len(changed), "events": len(changed) * 3}))


if __name__ == "__main__":
    main()
