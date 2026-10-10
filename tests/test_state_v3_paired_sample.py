import unittest

from scripts.prepare_state_v3_paired_sample import select_sample


class StateV3PairedSampleTest(unittest.TestCase):
    def test_selection_is_fixed_unique_and_outcome_independent(self):
        accepted = {f"S{i:02d}": {} for i in range(31)}
        families = (
            "emotion", "behavioral_disposition", "relationship",
            "consequence_risk",
        )
        e9 = [
            {
                "scenario_id": f"S{i:02d}",
                "changed_turn_count": 0,
                "state_family": families[i % 4],
            }
            for i in range(12)
        ]
        e1 = [
            {
                "scenario_id": f"S{i:02d}",
                "machine_directions_after_vote": {
                    "emotion.anxiety": "similar",
                    "relationship.trust": "similar",
                },
            }
            for i in range(8, 24)
        ]
        first = select_sample(accepted, e1, e9, seed="fixed")
        second = select_sample(accepted, e1, e9, seed="fixed")
        self.assertEqual(first, second)
        self.assertEqual(len(first["selected"]), 16)
        self.assertEqual(len(set(first["selected"])), 16)
        covered = set().union(*(
            set(value["state_families"])
            for value in first["e9_risk_details"].values()
        ))
        self.assertEqual(covered, set(families))


if __name__ == "__main__":
    unittest.main()
