"""Run free-form model policies against the canonical environment."""

from schemas.validate import validate_trajectory


class RolloutRunner:
    def __init__(self, environment_factory, logger=None):
        self.environment_factory = environment_factory
        self.logger = logger

    def run(self, policy, max_turns=None):
        environment = self.environment_factory()
        if hasattr(policy, "reset"):
            policy.reset()
        environment.reset()
        limit = max_turns or environment.scenario.get("max_turns", 20)
        while (
            environment.session["turn_id"] < limit
            and environment.session["status"] == "active"
        ):
            environment.step(policy.generate(environment.observe()))
        trajectory = environment.private_trajectory()
        trajectory["policy_id"] = policy.policy_id
        trajectory["policy_provenance"] = getattr(
            policy,
            "provenance",
            {"policy_id": policy.policy_id},
        )
        validate_trajectory(trajectory)
        if self.logger:
            self.logger.write(trajectory)
        return trajectory

    def run_many(self, policies, max_turns=None):
        return [self.run(policy, max_turns=max_turns) for policy in policies]
