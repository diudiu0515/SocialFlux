"""Batch rollout execution with policy/scenario provenance."""

from .runner import RolloutRunner


class BatchRolloutRunner:
    def __init__(self, scenario_factory, logger=None):
        self.scenario_factory = scenario_factory
        self.logger = logger

    def run(self, policies, runs_per_policy=1, max_turns=None):
        results = []
        for policy_factory in policies:
            for run_index in range(runs_per_policy):
                policy = policy_factory() if callable(policy_factory) else policy_factory
                runner = RolloutRunner(self.scenario_factory, self.logger)
                trajectory = runner.run(policy, max_turns=max_turns)
                trajectory["run_index"] = run_index
                results.append(trajectory)
        return results
