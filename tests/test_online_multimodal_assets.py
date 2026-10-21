import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from environment.online_multimodal import build_online_multimodal_profile
from environment.online_video_assets import (
    build_online_asset_request,
    online_identity_spec,
)
from scripts.audit_online_multimodal_triggerability import replay_scenario
from scripts.prepare_online_multimodal_assets import prepare
from scripts.run_autodl_seedance_video import materialize_local_references
from scripts.run_multimodal_video_queue import (
    filter_records_by_scenario,
    seedance_payload,
    select_records,
)
from scenario_design.catalog import discover_scenario_paths


SCENARIO_ROOT = Path("data/gpt50/experiment/scenario/scenarios")


def first_scenarios(count=2):
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in discover_scenario_paths(SCENARIO_ROOT)[:count]
    ]


class OnlineMultimodalAssetTest(unittest.TestCase):
    def test_identity_is_deterministic_and_scenario_specific(self):
        first, second = first_scenarios()
        one = online_identity_spec(first)
        self.assertEqual(one, online_identity_spec(first))
        self.assertNotEqual(
            one["identity_id"], online_identity_spec(second)["identity_id"]
        )

    def test_request_has_response_neutral_nonverbal_audio_and_english(self):
        scenario = first_scenarios(1)[0]
        request = build_online_asset_request(
            scenario, "open_engagement", duration_seconds=4
        )
        self.assertTrue(request["generate_audio"])
        self.assertTrue(request["prompt"].isascii())
        self.assertIn("does not speak", request["prompt"])
        self.assertIn("Audio is required", request["prompt"])
        self.assertTrue(request["audio"]["required"])
        self.assertFalse(request["audio"]["spoken_content"])
        self.assertIn(scenario["environment_agent"]["persona"]["name"], request["prompt"])
        self.assertFalse(any(request["safety_check"].values()))

    def test_event_families_use_distinct_medium_intensity_v3_cues(self):
        scenario = first_scenarios(1)[0]
        families = build_online_multimodal_profile(scenario)["event_families"]
        prompts = {
            family: build_online_asset_request(scenario, family)["prompt"]
            for family in families
        }
        self.assertEqual(len(prompts), len(set(prompts.values())))
        self.assertTrue(all(
            "unmistakably different" in prompt for prompt in prompts.values()
        ))
        weak_phrases = ("slightly", "only a few centimeters", "eases only slightly")
        self.assertTrue(all(
            phrase not in prompt
            for prompt in prompts.values()
            for phrase in weak_phrases
        ))


    def test_triggerability_audit_separates_hits_cooldown_and_dimensions(self):
        initial = {
            "emotion": {"anxiety": 5},
            "behavioral_disposition": {"resolve": 5},
            "relationship": {"trust": 5},
            "consequence_risk": {"goal_failure_risk": 5},
        }
        behavior_up = {**initial, "behavioral_disposition": {"resolve": 6}}
        relationship_up = {
            **behavior_up,
            "relationship": {"trust": 6},
        }
        states = [
            initial, behavior_up, behavior_up, relationship_up, relationship_up
        ]
        turns = []
        before = initial
        for index, after in enumerate(states, start=1):
            turns.append({
                "turn_id": f"t{index}",
                "state_before": before,
                "state_after": after,
                "dynamics_before": {},
                "dynamics_after": {},
            })
            before = after
        record = replay_scenario({
            "scenario_id": "triggerability-test",
            "initial_state": initial,
            "video_triggers": [],
        }, {"turns": turns}, Path("saved/trajectory.json"))
        self.assertEqual(record["event_count"], 2)
        self.assertEqual(record["first_fire_turn"], 2)
        self.assertEqual(record["triggerability_tier"], "easy")
        self.assertEqual(record["turns"][0]["condition_hit_count"], 0)
        self.assertGreater(record["blocked_reason_counts"]["global_cooldown"], 0)
        self.assertEqual(
            {event["source_state_family"] for event in record["events"]},
            {"behavioral_disposition", "relationship"},
        )

    def test_preparer_emits_all_required_families_and_anchor_dependencies(self):
        source = discover_scenario_paths(SCENARIO_ROOT)[0]
        scenario = json.loads(source.read_text(encoding="utf-8"))
        expected_families = set(
            build_online_multimodal_profile(scenario)["event_families"]
        )
        with TemporaryDirectory() as directory:
            batch = Path(directory)
            scenario_root = batch / "scenarios"
            destination = scenario_root / "scenario_001" / "scenario_001.json"
            destination.parent.mkdir(parents=True)
            shutil.copyfile(source, destination)
            prepare(SimpleNamespace(
                config=Path("configs/online_multimodal_assets.json"),
                scenario_root=scenario_root,
                expected_count=1,
                output=None,
                batch_root=batch,
            ))
            manifest = json.loads(
                (batch / "online_multimodal" / "manifest.json").read_text()
            )
            records = manifest["requests"]
            self.assertEqual(
                {item["event_family"] for item in records}, expected_families
            )
            self.assertEqual(manifest["anchor_request_count"], 1)
            anchor = next(
                item for item in records if item["dependency_phase"] == 0
            )
            dependents = [
                item for item in records if item["dependency_phase"] == 1
            ]
            self.assertEqual(anchor["event_family"], "activated_tension")
            self.assertTrue(dependents)
            self.assertTrue(all(
                item["reference_request_id"] == anchor["request_id"]
                for item in dependents
            ))
            pending = json.loads(
                (
                    batch
                    / "online_multimodal"
                    / "event_assets.pending.json"
                ).read_text()
            )
            self.assertFalse(pending["runtime_ready"])
            review = json.loads(
                (batch / "online_multimodal" / "asset_review.json").read_text()
            )
            checks = review["items"][0]["checks"]
            self.assertIn("audio_track_present", checks)
            self.assertIn("family_audio_cue_alignment", checks)
            self.assertIn("natural_synchronized_audio", checks)
            self.assertNotIn("no_audio_track", checks)

    def test_reference_video_is_materialized_only_for_submission(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "online_multimodal"
            reference = root / "assets" / "anchor.mp4"
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"fake-mp4-reference")
            provider_states = root / "provider_states"
            provider_states.mkdir()
            (provider_states / "anchor.json").write_text(json.dumps({
                "status": "downloaded",
                "video_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
                "latest_query_response": {
                    "content": {
                        "video_url": "https://assets.example.test/anchor.mp4"
                    }
                },
            }))
            payload = seedance_payload({
                "prompt": "A silent fictional adult makes one subtle natural movement.",
                "duration_seconds": 4,
                "generate_audio": False,
                "reference_video_file": "online_multimodal/assets/anchor.mp4",
            }, reference_root=Path(directory))
            self.assertFalse(payload["generate_audio"])
            self.assertEqual(payload["local_reference_video"], str(reference))
            materialized = materialize_local_references(payload)
            self.assertNotIn("local_reference_video", materialized)
            video = next(
                item for item in materialized["content"]
                if item["type"] == "video_url"
            )
            self.assertEqual(video["role"], "reference_video")
            self.assertEqual(
                video["video_url"]["url"],
                "https://assets.example.test/anchor.mp4",
            )

    def test_queue_selects_anchors_and_dependents_separately(self):
        manifest = {
            "requests": [
                {"request_id": "a", "dependency_phase": 0},
                {"request_id": "b", "dependency_phase": 1},
            ]
        }
        self.assertEqual(
            [item["request_id"] for item in select_records(
                Path("."), manifest, "anchors"
            )],
            ["a"],
        )
        self.assertEqual(
            [item["request_id"] for item in select_records(
                Path("."), manifest, "dependents"
            )],
            ["b"],
        )

    def test_scenario_limit_keeps_all_assets_for_selected_scenarios(self):
        records = [
            {"request_id": "a1", "scenario_id": "A"},
            {"request_id": "a2", "scenario_id": "A"},
            {"request_id": "b1", "scenario_id": "B"},
        ]
        selected = filter_records_by_scenario(records, scenario_limit=1)
        self.assertEqual(
            [item["request_id"] for item in selected], ["a1", "a2"]
        )


if __name__ == "__main__":
    unittest.main()
