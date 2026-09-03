"""The single canonical stateful environment for offline rollouts and online T4."""

from copy import deepcopy
import uuid

from .initializer import freeze_initialization
from .memory import MemoryModule
from .multimodal import ObservableExpressionLayer
from .state_updater import apply_transition
from .termination import check_termination


def coerce_free_form_action(action):
    if isinstance(action, str):
        result = {"text": action}
    elif isinstance(action, dict):
        result = deepcopy(action)
    else:
        raise TypeError("action must be text or an object containing text")
    text = str(result.get("text", "")).strip()
    if not text:
        raise ValueError("free-form action text must not be empty")
    if "action_id" in result:
        raise ValueError("action_id taxonomy is not accepted; submit arbitrary text")
    result["text"] = text
    return result


class StatefulEnvironment:
    def __init__(
        self,
        scenario,
        *,
        state_updater,
        response_generator,
        memory=None,
        provenance=None,
    ):
        if state_updater is None or response_generator is None:
            raise ValueError("canonical environment requires model-backed state and response components")
        self.scenario = deepcopy(scenario)
        self.state_updater = state_updater
        self.response_generator = response_generator
        self.memory = memory or MemoryModule()
        self.expression_layer = ObservableExpressionLayer(self.scenario)
        self.provenance = deepcopy(provenance or {
            "state_updater": getattr(state_updater, "provenance", {}),
            "response_generator": getattr(response_generator, "provenance", {}),
        })
        self.session = None

    def reset(self, episode_id=None):
        frozen = freeze_initialization(self.scenario)
        self.session = {
            "trajectory_id": episode_id or uuid.uuid4().hex,
            "scenario_id": self.scenario["scenario_id"],
            "turn_id": 0,
            "status": "active",
            "state": frozen["initial_state"],
            "dynamics": frozen["initial_dynamics"],
            "history": [],
            "turns": [],
            "ending": None,
            "current_response": self.scenario.get("opening_response", ""),
            "observable_cues": [],
            "observable_expression": deepcopy(self.expression_layer.default_expression),
            "media": [],
            "last_trigger_turns": {},
        }
        return self.observe()

    def observe(self):
        if self.session is None:
            raise RuntimeError("environment must be reset before observing")
        agent = self.scenario["environment_agent"]
        return {
            "scenario_id": self.scenario["scenario_id"],
            "role": deepcopy(self.scenario.get("evaluated_agent_role", {})),
            "background": self.scenario.get("background", ""),
            "explicit_goal": self.scenario.get("evaluated_agent_role", {}).get("explicit_goal", ""),
            "history": deepcopy(self.session["history"]),
            "current_response": self.session["current_response"],
            "observable_cues": deepcopy(self.session["observable_cues"]),
            "observable_expression": deepcopy(self.session["observable_expression"]),
            "media": deepcopy(self.session["media"]),
            "turn_id": self.session["turn_id"],
            "status": self.session["status"],
        }

    def snapshot(self):
        if self.session is None:
            raise RuntimeError("environment must be reset before snapshot")
        return deepcopy({
            key: self.session[key]
            for key in (
                "turn_id",
                "status",
                "state",
                "dynamics",
                "history",
                "ending",
                "current_response",
                "observable_cues",
                "observable_expression",
                "media",
                "last_trigger_turns",
            )
        })

    def restore(self, snapshot, episode_id=None):
        self.reset(episode_id=episode_id)
        for key, value in deepcopy(snapshot).items():
            if key in self.session and key not in ("trajectory_id", "scenario_id", "turns"):
                self.session[key] = value
        self.session["status"] = "active"
        self.session["ending"] = None
        self.session["turns"] = []
        return self.observe()

    def step(self, action):
        if self.session is None:
            raise RuntimeError("environment must be reset before stepping")
        if self.session["status"] != "active":
            raise ValueError("episode is not active")
        action = coerce_free_form_action(action)
        observation_before = self.observe()
        snapshot_before = self.snapshot()
        turn_id = self.session["turn_id"] + 1
        state_before = deepcopy(self.session["state"])
        dynamics_before = deepcopy(self.session["dynamics"])
        memory_view = self.memory.retrieve(self.session["history"], action)
        transition = self.state_updater.update(
            action=action,
            previous_state=state_before,
            previous_dynamics=dynamics_before,
            memory=memory_view,
        )
        state_after, dynamics_after, state_numeric, dynamics_numeric = apply_transition(
            state_before,
            dynamics_before,
            transition,
        )
        response_context = {
            "scenario": {
                "background": self.scenario["background"],
                "environment_agent": self.scenario["environment_agent"],
            },
            "turn_id": turn_id,
            "action": deepcopy(action),
            "memory": deepcopy(memory_view),
            "appraisal": deepcopy(transition["appraisal"]),
            "state": deepcopy(state_after),
            "dynamics": deepcopy(dynamics_after),
            "history": deepcopy(self.session["history"]),
        }
        response = self.response_generator.generate(response_context)
        multimodal = self.expression_layer.evaluate(
            turn_id=turn_id,
            previous_state=state_before,
            previous_dynamics=dynamics_before,
            state=state_after,
            dynamics=dynamics_after,
            last_trigger_turns=self.session["last_trigger_turns"],
        )
        self.session["history"].extend([
            {"turn_id": turn_id, "role": "evaluated_agent", "text": action["text"]},
            {"turn_id": turn_id, "role": "environment_agent", "text": response},
        ])
        self.session["turn_id"] = turn_id
        self.session["state"] = state_after
        self.session["dynamics"] = dynamics_after
        self.session["current_response"] = response
        self.session["observable_expression"] = multimodal["observable_expression"]
        self.session["media"] = multimodal["media"]
        self.session["observable_cues"] = deepcopy(
            multimodal["observable_expression"].get("behavioral_cues", [])
        )
        ended, reason = check_termination(
            turn_id,
            self.scenario.get("max_turns", 20),
            state_after,
            dynamics_after,
            self.scenario,
        )
        if ended:
            self.session["status"] = "completed"
            self.session["ending"] = {"reason": reason, "turn_id": turn_id}
        log = {
            "turn_id": f"t{turn_id}",
            "observation": observation_before,
            "policy_action": deepcopy(action),
            "memory_view": memory_view,
            "appraisal": transition["appraisal"],
            "evidence_turn_ids": transition["evidence_turn_ids"],
            "state_before": state_before,
            "state_delta": transition["state_delta"],
            "state_after": state_after,
            "dynamics_before": dynamics_before,
            "dynamics_delta": transition["interaction_dynamics_delta"],
            "dynamics_after": dynamics_after,
            "numeric_state_delta": state_numeric,
            "numeric_dynamics_delta": dynamics_numeric,
            "environment_response": response,
            "trigger_events": multimodal["private_events"],
            "observable_expression": multimodal["observable_expression"],
            "media": multimodal["media"],
            "environment_snapshot_before": snapshot_before,
        }
        log["observation_after"] = self.observe()
        self.session["turns"].append(log)
        return deepcopy(log["observation_after"]), log

    def private_trajectory(self):
        if self.session is None:
            raise RuntimeError("environment must be reset before reading trajectory")
        return deepcopy({
            "trajectory_id": self.session["trajectory_id"],
            "scenario_id": self.session["scenario_id"],
            "policy_id": None,
            "policy_provenance": {},
            "environment_provenance": self.provenance,
            "initial_state": self.scenario["initial_state"],
            "initial_dynamics": self.scenario.get("initial_dynamics", {}),
            "turns": self.session["turns"],
            "ending": self.session["ending"],
        })
