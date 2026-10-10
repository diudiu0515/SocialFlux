"""The single canonical stateful environment for offline rollouts and online T4."""

from copy import deepcopy
import inspect
import uuid

from .initializer import freeze_initialization
from .interaction_ledger import (
    initial_ledger,
    record_environment_response,
    record_evaluated_action,
)
from .longitudinal import (
    initialize_longitudinal_session,
    maybe_advance_segment,
    public_longitudinal_view,
)
from .memory import MemoryModule
from .multimodal import ObservableExpressionLayer
from .observation import (
    build_policy_observation,
    build_public_evaluated_role,
)
from .public_situation import build_environment_situation, environment_background
from .state_updater import apply_transition
from .appraisal_context import build_appraisal_context
from .policy_context import shared_initial_background
from .state_opportunity import (
    STATE_OPPORTUNITY_PROFILE_V1,
    STATE_OPPORTUNITY_PROFILE_V2,
    STATE_OPPORTUNITY_PROFILE_V3,
    STATE_OPPORTUNITY_PROFILE_V4,
    STATE_OPPORTUNITY_PROFILE_V5,
    STATE_OPPORTUNITY_PROFILE_V6,
    build_state_transition_opportunity,
)
from .termination import check_termination
from .video_requests import attach_online_requests


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
        minimum_natural_turns=1,
        response_opportunity_guidance=True,
        multimodal_trigger_policy=None,
    ):
        if state_updater is None or response_generator is None:
            raise ValueError("canonical environment requires model-backed state and response components")
        self.scenario = deepcopy(scenario)
        self.state_updater = state_updater
        self.response_generator = response_generator
        self.minimum_natural_turns = int(minimum_natural_turns)
        self.response_opportunity_guidance = bool(response_opportunity_guidance)
        self.memory = memory or MemoryModule()
        self.expression_layer = ObservableExpressionLayer(
            self.scenario, multimodal_trigger_policy
        )
        self.provenance = deepcopy(provenance or {
            "state_updater": getattr(state_updater, "provenance", {}),
            "response_generator": getattr(response_generator, "provenance", {}),
        })
        self.session = None

    def reset(self, episode_id=None, event_selection_key=None):
        frozen = freeze_initialization(self.scenario)
        trajectory_id = episode_id or uuid.uuid4().hex
        self.session = {
            "trajectory_id": trajectory_id,
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
            "interaction_ledger": initial_ledger(
                shared_initial_background(self.scenario),
                self.scenario.get("evaluated_agent_role", {}).get("explicit_goal", ""),
                self.scenario.get("narrative_design", {}).get(
                    "meaningful_choice_space", []
                ),
            ),
            **initialize_longitudinal_session(
                self.scenario, trajectory_id, event_selection_key
            ),
        }
        return self.observe()

    def observe(self):
        if self.session is None:
            raise RuntimeError("environment must be reset before observing")
        return build_policy_observation(self.scenario, self.session)

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
                "interaction_ledger",
                "longitudinal_enabled",
                "elapsed_time",
                "time_unit",
                "segment_index",
                "segment_turn_id",
                "current_segment",
                "segments",
                "public_timeline",
                "event_plan",
                "counterfactual_timeline_lock",
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

    def step(self, action, *, controlled_observation=None):
        frame = self._begin_turn(action)
        transition_result = self._run_state_update(frame)
        response_result = self._run_response_stage(
            frame,
            transition_result,
            controlled_observation,
        )
        self._commit_turn(frame, transition_result, response_result)
        segment_transition = self._finish_turn(
            frame,
            transition_result,
            response_result,
        )
        log = self._build_turn_log(
            frame,
            transition_result,
            response_result,
            segment_transition,
        )
        self.session["turns"].append(log)
        return deepcopy(log["observation_after"]), log

    def _begin_turn(self, action):
        if self.session is None:
            raise RuntimeError("environment must be reset before stepping")
        if self.session["status"] != "active":
            raise ValueError("episode is not active")
        return {
            "action": coerce_free_form_action(action),
            "observation_before": self.observe(),
            "snapshot_before": self.snapshot(),
            "turn_id": self.session["turn_id"] + 1,
            "segment_before": deepcopy(self.session.get("current_segment", {})),
            "segment_turn_before": int(self.session.get("segment_turn_id", 0)),
            "elapsed_before": self.session.get("elapsed_time", 0),
            "state_before": deepcopy(self.session["state"]),
            "dynamics_before": deepcopy(self.session["dynamics"]),
            "ledger_before": deepcopy(self.session["interaction_ledger"]),
        }

    def _run_state_update(self, frame):
        action = frame["action"]
        memory_view = self.memory.retrieve(self.session["history"], action)
        # The action has already been coerced/finalized in _begin_turn.  Only
        # now regenerate repetition matches; they are evidence matches, not
        # a proxy for whether an earlier numeric update happened.
        appraisal_context = build_appraisal_context(
            history=self.session["history"],
            turns=self.session["turns"],
            action=action,
            current_turn_id=frame["turn_id"],
            interaction_ledger=frame["ledger_before"],
            longitudinal_context=public_longitudinal_view(self.session),
        )
        memory_view["duplicate_evidence_matches"] = deepcopy(
            appraisal_context["duplicate_evidence_matches"]
        )
        # Keep the old ID field only as an audit compatibility view.
        memory_view["deterministic_surface_duplicate_ids"] = [
            item["historical_turn_id"]
            for item in appraisal_context["duplicate_evidence_matches"]
        ]
        update_kwargs = {
            "action": action,
            "previous_state": frame["state_before"],
            "previous_dynamics": frame["dynamics_before"],
            "memory": memory_view,
        }
        update_parameters = inspect.signature(self.state_updater.update).parameters
        if "appraisal_context" in update_parameters:
            update_kwargs["appraisal_context"] = appraisal_context
        if "longitudinal_context" in update_parameters:
            update_kwargs["longitudinal_context"] = public_longitudinal_view(
                self.session
            )
        if "interaction_ledger" in update_parameters:
            update_kwargs["interaction_ledger"] = frame["ledger_before"]
        if "current_event_id" in update_parameters:
            update_kwargs["current_event_id"] = f"t{frame['turn_id']}"
        try:
            transition = self.state_updater.update(**update_kwargs)
        except Exception as exc:
            exc.failed_turn_context = {
                "turn_id": f"t{frame['turn_id']}",
                "policy_action": deepcopy(action),
                "memory_view": deepcopy(memory_view),
                "appraisal_context": deepcopy(appraisal_context),
                "longitudinal_context": public_longitudinal_view(self.session),
            }
            raise

        # This is the deterministic boundary between the two independent LLM calls.
        state_after, dynamics_after, state_numeric, dynamics_numeric = apply_transition(
            frame["state_before"],
            frame["dynamics_before"],
            transition,
        )
        response_ledger = record_evaluated_action(
            frame["ledger_before"],
            turn_id=frame["turn_id"],
            action=action,
            appraisal=transition["appraisal"],
            semantic_events=transition["appraisal"].get("ledger_events"),
        )
        return {
            "transition": transition,
            "memory_view": memory_view,
            "appraisal_context": appraisal_context,
            "state_after": state_after,
            "dynamics_after": dynamics_after,
            "state_numeric": state_numeric,
            "dynamics_numeric": dynamics_numeric,
            "response_ledger": response_ledger,
        }

    def _run_response_stage(
        self,
        frame,
        transition_result,
        controlled_observation,
    ):
        transition = transition_result["transition"]
        response_ledger = transition_result["response_ledger"]
        response_prompt_id = getattr(self.response_generator, "prompt_id", None)
        opportunity_profile = {
            "environment_response_v26": STATE_OPPORTUNITY_PROFILE_V1,
            "environment_response_v27": (
                STATE_OPPORTUNITY_PROFILE_V3
                if self.provenance.get(
                    "state_transition_runtime_revision"
                ) == "v3.2"
                else STATE_OPPORTUNITY_PROFILE_V2
            ),
            "environment_response_v27_decision_continuity": (
                STATE_OPPORTUNITY_PROFILE_V2
            ),
            "environment_response_v28": STATE_OPPORTUNITY_PROFILE_V4,
            "environment_response_v29_event_driven": (
                STATE_OPPORTUNITY_PROFILE_V5
            ),
            "environment_response_v30_semantic_event_driven": (
                STATE_OPPORTUNITY_PROFILE_V6
            ),
            "environment_response_v31_contrastive_event_driven": (
                STATE_OPPORTUNITY_PROFILE_V6
            ),
        }.get(response_prompt_id)
        if not self.response_opportunity_guidance:
            opportunity_profile = None
        state_transition_opportunity = (
            build_state_transition_opportunity(
                self.scenario,
                self.session.get("turns", []),
                transition_result["state_numeric"],
                frame["turn_id"],
                profile=opportunity_profile,
            )
            if opportunity_profile is not None
            else None
        )
        context = {
            "scenario": {
                "background": environment_background(self.scenario),
                "public_situation": build_environment_situation(self.scenario),
                "environment_agent": self.scenario["environment_agent"],
                "evaluated_agent_role": build_public_evaluated_role(
                    self.scenario["evaluated_agent_role"]
                ),
            },
            "turn_id": frame["turn_id"],
            "action": deepcopy(frame["action"]),
            "memory": deepcopy(transition_result["memory_view"]),
            "appraisal": deepcopy(transition["appraisal"]),
            "state": deepcopy(transition_result["state_after"]),
            "dynamics": deepcopy(transition_result["dynamics_after"]),
            "history": deepcopy(self.session["history"]),
            "interaction_ledger": deepcopy(response_ledger),
            "longitudinal_context": public_longitudinal_view(self.session),
        }
        if state_transition_opportunity is not None:
            context["state_transition_opportunity"] = deepcopy(
                state_transition_opportunity
            )
        if controlled_observation is not None:
            context["controlled_observation"] = deepcopy(controlled_observation)
        try:
            generated = self.response_generator.generate(context)
        except Exception as exc:
            exc.failed_turn_context = {
                "turn_id": f"t{frame['turn_id']}",
                "policy_action": deepcopy(frame["action"]),
                "appraisal": deepcopy(transition["appraisal"]),
                "interaction_ledger": deepcopy(response_ledger),
            }
            raise

        if isinstance(generated, dict):
            return {
                "text": str(generated["response_text"]).strip(),
                "ledger_events": deepcopy(generated["ledger_events"]),
                "ledger_normalizations": deepcopy(
                    generated.get("ledger_event_normalizations", [])
                ),
                "request_retry_diagnostics": deepcopy(
                    generated.get("request_retry_diagnostics", [])
                ),
                "reply_obligation": generated.get("reply_obligation"),
                "consequential_claims": deepcopy(
                    generated.get("consequential_claims", [])
                ),
                "expression_intent": generated.get("expression_intent"),
                "observable_behavior": deepcopy(
                    generated.get("observable_behavior")
                ),
                "state_transition_opportunity": deepcopy(
                    state_transition_opportunity
                ),
                "controlled_observation": deepcopy(controlled_observation),
            }
        return {
            "text": str(generated).strip(),
            "ledger_events": None,
            "ledger_normalizations": [],
            "request_retry_diagnostics": [],
            "reply_obligation": None,
            "consequential_claims": [],
            "expression_intent": None,
            "observable_behavior": None,
            "state_transition_opportunity": deepcopy(
                state_transition_opportunity
            ),
            "controlled_observation": deepcopy(controlled_observation),
        }

    def _commit_turn(self, frame, transition_result, response_result):
        transition = transition_result["transition"]
        text = response_result["text"]
        ledger_after = record_environment_response(
            transition_result["response_ledger"],
            turn_id=frame["turn_id"],
            response=text,
            latest_social_act=transition["appraisal"].get("social_act", "other"),
            latest_action=frame["action"].get("text", ""),
            semantic_events=response_result["ledger_events"],
        )
        multimodal = self.expression_layer.evaluate(
            turn_id=frame["turn_id"],
            previous_state=frame["state_before"],
            previous_dynamics=frame["dynamics_before"],
            state=transition_result["state_after"],
            dynamics=transition_result["dynamics_after"],
            last_trigger_turns=self.session["last_trigger_turns"],
        )
        response_neutral_event = any(
            event.get("response_neutral")
            for event in multimodal["private_events"]
        )
        if response_result["observable_behavior"] is not None and not response_neutral_event:
            multimodal["observable_expression"] = deepcopy(
                response_result["observable_behavior"]
            )
        multimodal = attach_online_requests(self.scenario, multimodal, text)
        controlled = response_result["controlled_observation"]
        if controlled is not None:
            multimodal["media"] = deepcopy(controlled.get("media", []))

        self.session["history"].extend([
            {
                "turn_id": frame["turn_id"],
                "role": "evaluated_agent",
                "text": frame["action"]["text"],
            },
            {
                "turn_id": frame["turn_id"],
                "role": "environment_agent",
                "text": text,
            },
        ])
        self.session.update({
            "turn_id": frame["turn_id"],
            "segment_turn_id": frame["segment_turn_before"] + 1,
            "state": transition_result["state_after"],
            "dynamics": transition_result["dynamics_after"],
            "interaction_ledger": ledger_after,
            "current_response": text,
            "observable_expression": multimodal["observable_expression"],
            "media": multimodal["media"],
            "video_api_requests": multimodal.get("video_api_requests", []),
            "observable_cues": deepcopy(
                multimodal["observable_expression"].get("behavioral_cues", [])
            ),
        })
        response_result["ledger_after"] = ledger_after
        response_result["multimodal"] = multimodal

    def _finish_turn(self, frame, transition_result, response_result):
        transition = transition_result["transition"]
        ledger_after = response_result["ledger_after"]
        continuation = (
            transition["appraisal"].get("dialogue_diagnostics", {})
            .get("continuation", {})
        )
        after_direct = continuation.get("after_direct_response") or {}
        answered_then_can_close = (
            continuation.get("status") == "must_answer"
            and after_direct.get("status") == "can_close"
        )
        natural_completion = (
            getattr(self.response_generator, "horizon_mode", None)
            == "natural_max_20"
            and frame["turn_id"] >= self.minimum_natural_turns
            and not self.session.get("longitudinal_enabled")
            and (ledger_after.get("latest_obligation") or {}).get("owner")
            != "evaluated_agent"
            and (
                continuation.get("status") == "can_close"
                or answered_then_can_close
            )
        )
        if natural_completion:
            ended, reason = True, "natural_completion"
        else:
            ended, reason = check_termination(
                frame["turn_id"],
                self.scenario.get("max_turns", 20),
                transition_result["state_after"],
                transition_result["dynamics_after"],
                self.scenario,
            )
        if ended:
            self.session["status"] = "completed"
            self.session["ending"] = {
                "reason": reason,
                "turn_id": frame["turn_id"],
            }
            return None
        return maybe_advance_segment(
            self.scenario,
            self.session,
            action_text=frame["action"]["text"],
            response_text=response_result["text"],
            appraisal=transition["appraisal"],
            response_events=response_result["ledger_events"],
        )

    def _build_turn_log(
        self,
        frame,
        transition_result,
        response_result,
        segment_transition,
    ):
        transition = transition_result["transition"]
        multimodal = response_result["multimodal"]
        log = {
            "turn_id": f"t{frame['turn_id']}",
            "segment_id": frame["segment_before"].get(
                "segment_id", "single_interaction"
            ),
            "segment_turn_id": frame["segment_turn_before"] + 1,
            "elapsed_time_before": frame["elapsed_before"],
            "observation": frame["observation_before"],
            "policy_action": deepcopy(frame["action"]),
            "memory_view": transition_result["memory_view"],
            "appraisal_context": deepcopy(transition_result.get("appraisal_context", {})),
            "appraisal": transition["appraisal"],
            "state_judgments": deepcopy(transition.get("state_judgments", [])),
            "dynamics_judgments": deepcopy(transition.get("dynamics_judgments", [])),
            "appraisal_request_retry_diagnostics": deepcopy(
                transition.get("appraisal_request_retry_diagnostics", [])
            ),
            "evidence_turn_ids": transition["evidence_turn_ids"],
            "calibration": deepcopy(transition.get("calibration", {})),
            "response_expression_intent": response_result["expression_intent"],
            "response_observable_behavior": response_result["observable_behavior"],
            "state_transition_opportunity": deepcopy(
                response_result.get("state_transition_opportunity")
            ),
            "state_before": frame["state_before"],
            "state_delta": transition["state_delta"],
            "state_after": transition_result["state_after"],
            "dynamics_before": frame["dynamics_before"],
            "dynamics_delta": transition["interaction_dynamics_delta"],
            "dynamics_after": transition_result["dynamics_after"],
            "numeric_state_delta": transition_result["state_numeric"],
            "numeric_dynamics_delta": transition_result["dynamics_numeric"],
            "environment_response_ledger_event_normalizations": (
                response_result["ledger_normalizations"]
            ),
            "response_request_retry_diagnostics": deepcopy(
                response_result["request_retry_diagnostics"]
            ),
            "response_reply_obligation": response_result["reply_obligation"],
            "response_consequential_claims": deepcopy(
                response_result["consequential_claims"]
            ),
            "interaction_ledger_before": frame["ledger_before"],
            "interaction_ledger_after": response_result["ledger_after"],
            "environment_response": response_result["text"],
            "environment_response_ledger_events": response_result["ledger_events"],
            "trigger_events": multimodal["private_events"],
            "video_api_requests": deepcopy(
                multimodal.get("video_api_requests", [])
            ),
            "observable_expression": multimodal["observable_expression"],
            "media": multimodal["media"],
            "environment_snapshot_before": frame["snapshot_before"],
            "segment_transition_after": deepcopy(segment_transition),
            "state_after_public_events": deepcopy(self.session["state"]),
            "dynamics_after_public_events": deepcopy(self.session["dynamics"]),
            "interaction_ledger_after_public_events": deepcopy(
                self.session["interaction_ledger"]
            ),
            "elapsed_time_after": self.session.get("elapsed_time", 0),
        }
        log["observation_after"] = self.observe()
        for key in ("state_appraisal_call", "interaction_appraisal_call", "combined_appraisal_call"):
            if key in transition:
                log[key] = deepcopy(transition[key])
        return log

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
            "longitudinal_design_version": (
                self.scenario.get("longitudinal_design", {}).get("format")
            ),
            "event_plan": self.session.get("event_plan", {}),
            "segments": self.session.get("segments", []),
            "public_timeline": self.session.get("public_timeline", []),
            "turns": self.session["turns"],
            "ending": self.session["ending"],
        })
