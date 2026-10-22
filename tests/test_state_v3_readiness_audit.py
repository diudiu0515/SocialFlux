import unittest

from scripts.audit_state_v3_readiness import tokens


def actor_suspect(
    rationale,
    environment_name,
    evaluated_name,
    environment_persona,
    evaluated_persona,
):
    folded = rationale.casefold()
    env_named = environment_name.casefold() in folded
    evaluated_named = evaluated_name.casefold() in folded
    rationale_tokens = tokens(rationale)
    env_overlap = len(rationale_tokens & tokens(environment_persona))
    evaluated_overlap = len(rationale_tokens & tokens(evaluated_persona))
    return (evaluated_named and not env_named) or (
        not env_named
        and not evaluated_named
        and evaluated_overlap >= env_overlap + 3
    )


class StateV3ReadinessAuditTest(unittest.TestCase):
    def test_explicit_environment_name_overrides_shared_vocabulary(self):
        rationale = (
            "Inez Calder's anxiety is high because the reporter, source, "
            "publication, and investigation remain uncertain."
        )
        self.assertFalse(actor_suspect(
            rationale,
            "Inez Calder",
            "Sami Osei",
            {"name": "Inez Calder"},
            {
                "name": "Sami Osei",
                "role": "reporter source publication investigation",
            },
        ))

    def test_evaluated_name_without_environment_name_is_suspect(self):
        self.assertTrue(actor_suspect(
            "Sami Osei's anxiety increases before publication.",
            "Inez Calder",
            "Sami Osei",
            {"name": "Inez Calder"},
            {"name": "Sami Osei"},
        ))


if __name__ == "__main__":
    unittest.main()
