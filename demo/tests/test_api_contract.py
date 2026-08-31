import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "demo"))
import server


class ParticipantContractTest(unittest.TestCase):
    def test_participant_payload_contains_only_observable_state(self):
        session = server.E.new_session()
        payload = server.participant(session)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("latent_values", serialized)
        self.assertNotIn("current_state", serialized)
        self.assertNotIn("hidden_intentions", serialized)
        self.assertNotIn("internal_research_log", serialized)
        self.assertIn("conversation", payload)
        self.assertIn("state_observation", payload)


if __name__ == "__main__":
    unittest.main()
