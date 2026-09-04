import json
import unittest

from offline.candidate_generation import ModelCandidateGenerator


class SequenceProvider:
    provenance = {"provider": "test", "model": "test"}

    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0

    def complete(self, messages, **sampling):
        self.calls += 1
        return json.dumps(next(self.outputs), ensure_ascii=False)


class CandidateGenerationTest(unittest.TestCase):
    def test_shared_observation_retries_target_self_address(self):
        bad = {
            "current_response": "林主管，你先解释。", "observable_cues": [],
            "observable_expression": {}, "media": [],
        }
        good = {
            "current_response": "你先把记录逐项解释清楚。", "observable_cues": [],
            "observable_expression": {}, "media": [],
        }
        provider = SequenceProvider([bad, good])
        generator = ModelCandidateGenerator(provider, {"seed": 1})
        result = generator.shared_observation(
            [], [],
            {"name": "林主管", "role": "值班主管"},
            {"name": "新员工", "role": "交接人"},
        )
        self.assertEqual(result, good)
        self.assertEqual(provider.calls, 2)


if __name__ == "__main__":
    unittest.main()
