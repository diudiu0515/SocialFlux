"""Public-only Task4 stepping for human, policy and future RL clients."""

from copy import deepcopy
from pathlib import Path
import threading
import uuid

from environment.qwen_task4 import request_providers
from shared.artifacts import atomic_json


class SessionConflict(ValueError):
    pass


class QwenTask4Session:
    """Persist private evidence locally; never put it in the client observation.

    reward=None deliberately means no reward function has been selected. It is
    not a zero reward or a task score. Consumers must attach an explicit reward
    function before optimizing a policy.
    """

    def __init__(self, factory, output):
        self.episode_id = uuid.uuid4().hex
        self.environment = factory()
        self.output = Path(output) / self.episode_id
        self.output.mkdir(parents=True, exist_ok=False)
        self.lock = threading.Lock()
        self.failed = False
        self.environment.reset(episode_id=self.episode_id)
        atomic_json(self.output / "provenance.json", self.environment.provenance)
        self._save_private()

    def _save_private(self):
        atomic_json(self.output / "trajectory.json", self.environment.private_trajectory())
        for stage, provider in request_providers(self.environment).items():
            atomic_json(self.output / (stage + "_requests.json"), provider.audit_records)

    def result(self):
        ending = self.environment.session.get("ending") or {}
        return {
            "episode_id": self.episode_id,
            "observation": self.environment.observe(),
            "reward": None,
            "terminated": ending.get("reason") == "natural_completion",
            "truncated": bool(ending) and ending.get("reason") != "natural_completion",
            "failed": self.failed,
            "info": {"reward_status": "unconfigured", "formal_admission": False},
        }

    def step(self, text, *, expected_turn_id):
        if not isinstance(text, str) or not text.strip():
            raise ValueError("action text must be nonempty")
        if isinstance(expected_turn_id, bool) or not isinstance(expected_turn_id, int):
            raise ValueError("expected_turn_id must be an integer")
        with self.lock:
            if self.failed or self.environment.session["status"] != "active":
                raise SessionConflict("episode is no longer active")
            if expected_turn_id != self.environment.session["turn_id"]:
                raise SessionConflict("stale turn; read the current observation before stepping")
            before = deepcopy(self.environment.session)
            atomic_json(self.output / "step_status.json", {
                "status": "in_progress", "turn_id": expected_turn_id + 1,
                "action": {"text": text.strip()},
            })
            try:
                self.environment.step({"text": text.strip()})
            except Exception as exc:
                # Preserve the failed action and all HTTP attempts. No hidden
                # retries or replacement actions, and no private error in API.
                self.failed = True
                atomic_json(self.output / "failure.json", {
                    "action": {"text": text.strip()}, "turn_id": expected_turn_id + 1,
                    "error_type": type(exc).__name__, "error": str(exc),
                    "diagnostics": list(getattr(exc, "diagnostics", [])),
                    "failed_session": self.environment.session,
                    "formal_admission": False,
                })
                self.environment.session = before
            finally:
                self._save_private()
                atomic_json(self.output / "step_status.json", {
                    "status": "failed" if self.failed else "completed",
                    "turn_id": expected_turn_id + 1,
                })
            return self.result()
