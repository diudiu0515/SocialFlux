"""Stateful online environment with public observations and complete private logs."""

from copy import deepcopy
import uuid

from .memory import MemoryModule
from .multimodal import ObservableExpressionLayer
from .initializer import freeze_initialization
from .response_generator import TemplateResponseGenerator
from .state_updater import RuleBasedStateUpdater, apply_transition
from .termination import check_termination


class StatefulEnvironment:
    def __init__(self, scenario, state_updater=None, response_generator=None, memory=None):
        self.scenario = deepcopy(scenario)
        self.state_updater = state_updater or RuleBasedStateUpdater(self.scenario)
        self.response_generator = response_generator or TemplateResponseGenerator(self.scenario)
        self.memory = memory or MemoryModule()
        self.expression_layer = ObservableExpressionLayer(self.scenario)
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
            "explicit_goal": agent.get("explicit_goal", ""),
            "history": deepcopy(self.session["history"]),
            "current_response": self.session["current_response"],
            "observable_cues": deepcopy(self.session["observable_cues"]),
            "observable_expression": deepcopy(self.session["observable_expression"]),
            "media": deepcopy(self.session["media"]),
            "turn_id": self.session["turn_id"],
            "status": self.session["status"],
        }

    def step(self, action):
        if self.session is None:
            raise RuntimeError("environment must be reset before stepping")
        if self.session["status"] != "active":
            raise ValueError("episode is not active")
        observation_before = self.observe()
        turn_id = self.session["turn_id"] + 1
        state_before = deepcopy(self.session["state"])
        dynamics_before = deepcopy(self.session["dynamics"])
        action_text = action.get("text", "") if isinstance(action, dict) else str(action)
        memory_view = self.memory.retrieve(self.session["history"], action)
        transition = self.state_updater.update(
            action=action,
            previous_state=state_before,
            previous_dynamics=dynamics_before,
            memory=memory_view,
        )
        state_after, dynamics_after, state_numeric, dynamics_numeric = apply_transition(
            state_before, dynamics_before, transition
        )
        response = self.response_generator.generate({
            "turn_id": turn_id,
            "action": deepcopy(action),
            "memory": deepcopy(memory_view),
            "state": deepcopy(state_after),
            "dynamics": deepcopy(dynamics_after),
            "history": deepcopy(self.session["history"]),
        })
        multimodal = self.expression_layer.evaluate(
            turn_id=turn_id,
            previous_state=state_before,
            previous_dynamics=dynamics_before,
            state=state_after,
            dynamics=dynamics_after,
            last_trigger_turns=self.session["last_trigger_turns"],
        )
        self.session["history"].extend([
            {"turn_id": turn_id, "role": "evaluated_agent", "text": action_text},
            {"turn_id": turn_id, "role": "environment_agent", "text": response},
        ])
        self.session["turn_id"] = turn_id
        self.session["state"], self.session["dynamics"] = state_after, dynamics_after
        self.session["current_response"] = response
        self.session["observable_expression"] = multimodal["observable_expression"]
        self.session["media"] = multimodal["media"]
        action_id = action.get("action_id") if isinstance(action, dict) else "default"
        self.session["observable_cues"] = deepcopy(
            self.scenario.get("observable_cues_by_action", {}).get(action_id, [])
        )
        ended, reason = check_termination(
            turn_id, self.scenario.get("max_turns", 20), state_after, dynamics_after, self.scenario
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
        }
        self.session["turns"].append(log)
        return self.observe(), log

    def private_trajectory(self):
        if self.session is None:
            raise RuntimeError("environment must be reset before reading trajectory")
        return deepcopy({
            "trajectory_id": self.session["trajectory_id"],
            "scenario_id": self.session["scenario_id"],
            "policy_id": None,
            "initial_state": self.scenario["initial_state"],
            "initial_dynamics": self.scenario.get("initial_dynamics", {}),
            "turns": self.session["turns"],
            "ending": self.session["ending"],
        })
