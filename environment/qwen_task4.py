"""Explicit Qwen Task4 profile over the existing canonical environment.

All changes are opt-in. Existing GPT/Claude factories, prompts, validators and
provider classes are untouched. RolloutRunner can use this factory directly;
human/RL clients can use QwenTask4Session for a public-only step interface.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from environment.qwen_task4_contract import (
    state_schema, interaction_schema, response_schema, retry_feedback,
)
from environment.unified_appraisal import UnifiedEnvironmentFactory
from pipeline.runtime import build_environment_factory
from providers.local_vllm import LocalVLLMProvider

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "qwen_task4_thinking_v1"
DEFAULT_CONFIG = ROOT / "configs/qwen_task4/environment.json"
STAGES = ("state", "interaction", "response")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config(path=DEFAULT_CONFIG):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("profile") != PROFILE or config.get("max_turns") != 20:
        raise ValueError("Expected the explicit Qwen Task4 profile with a 20-turn maximum")
    env = config["environment"]
    required = {
        "independent_appraisals": True,
        "state_appraisal_prompt_id": "environment_state_appraisal_v6_observed_evidence",
        "interaction_appraisal_prompt_id": "environment_interaction_appraisal_v1",
        "response_prompt_id": "environment_response_v31_contrastive_event_driven",
        "response_validation_profile": "hard_only",
        "state_calibration_profile": "state_judgment_primary_hysteretic_v7",
    }
    if any(env.get(key) != value for key, value in required.items()):
        raise ValueError("Qwen Task4 canonical base contract mismatch")
    for key in ("provider", "state_appraisal_provider", "interaction_appraisal_provider", "response_provider"):
        provider = env[key]
        if (provider.get("provider") != "local_vllm"
                or provider.get("model") != config["model"]
                or not provider["model"].startswith("Qwen/")
                or urlparse(provider["endpoint"]).hostname not in {"127.0.0.1", "localhost", "::1"}
                or provider.get("max_transport_attempts") != 1
                or provider.get("stream", False)):
            raise ValueError("Qwen Task4 requires one bounded local Qwen route per stage")
    for stage in STAGES:
        sampling = env[stage + ("_sampling" if stage == "response" else "_appraisal_sampling")]
        budget = sampling.get("thinking_token_budget")
        if (isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0
                or sampling.get("max_tokens", 0) - budget < 2048
                or sampling.get("chat_template_kwargs") != {"enable_thinking": True, "reasoning_effort": "medium"}):
            raise ValueError(f"{stage} requires bounded medium thinking and at least 2048 final tokens")
    return config


def load_prompt_profile(config):
    path = ROOT / config["prompt_manifest"]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("profile") != PROFILE or set(manifest["prompts"]) != set(STAGES):
        raise ValueError("Qwen prompt manifest mismatch")
    prompts = {}
    for stage, spec in manifest["prompts"].items():
        prompt_path = ROOT / spec["path"]
        if digest(prompt_path) != spec["sha256"]:
            raise ValueError(f"Qwen {stage} prompt checksum mismatch")
        prompts[stage] = prompt_path.read_text(encoding="utf-8")
    for filename, expected in manifest["base_sha256"].items():
        if digest(ROOT / filename) != expected:
            raise ValueError("Qwen base contract changed; create and review a new profile: " + filename)
    return prompts, manifest, digest(path)


class QwenTask4Provider(LocalVLLMProvider):
    """Only changes request instructions; canonical code owns every retry."""

    def __init__(self, *, stage, instruction, profile_sha256, **config):
        config = deepcopy(config)
        if config.pop("provider") != "local_vllm":
            raise ValueError("Qwen interface requires local_vllm")
        super().__init__(**config)
        self.stage = stage
        self.instruction = instruction
        self.profile_sha256 = profile_sha256

    @property
    def provenance(self):
        return {**super().provenance, "qwen_interface_profile": PROFILE,
                "qwen_stage": self.stage, "qwen_prompt_manifest_sha256": self.profile_sha256}

    def prepare_messages(self, messages):
        result = deepcopy(messages)
        if self.stage in {"state", "interaction"}:
            prefix, separator, encoded = result[1]["content"].partition("## Input\n")
            if not separator:
                raise ValueError("Missing canonical appraisal input boundary")
            payload = json.loads(encoded)
            schema = state_schema(payload) if self.stage == "state" else interaction_schema(payload)
        else:
            schema = response_schema()
        result[0]["content"] += (
            "\n\n" + self.instruction + "\nOutput schema (JSON Schema):\n"
            + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        )
        if len(result) >= 4 and result[-2].get("role") == "assistant" and result[-1].get("role") == "user":
            result[-1]["content"] += (
                "\nQwen field diagnostics for that rejected candidate:\n"
                + retry_feedback(result[-2]["content"], schema)
            )
        return result

    def complete(self, messages, **generation):
        # The inherited provider logs these final wire messages and actual token
        # usage. There is no output rewriting, secondary sampling or fallback.
        return super().complete(self.prepare_messages(messages), **generation)


class QwenTask4EnvironmentFactory(UnifiedEnvironmentFactory):
    def __init__(self, scenario, config_path=DEFAULT_CONFIG):
        self.config = load_config(config_path)
        self.instructions, self.prompt_profile, self.prompt_profile_sha = load_prompt_profile(self.config)
        self.config_sha = digest(config_path)
        super().__init__(build_environment_factory(scenario, self.config["environment"]))

    @property
    def provenance(self):
        return {**super().provenance,
                "qwen_task4_profile": PROFILE, "qwen_config_sha256": self.config_sha,
                "qwen_prompt_manifest_sha256": self.prompt_profile_sha,
                "qwen_prompt_profile": deepcopy(self.prompt_profile),
                "model_weight_revision": self.config["model_weight_revision"],
                "formal_admission": False, "human_review_status": "pending"}

    def __call__(self):
        environment = super().__call__()
        config = self.config["environment"]
        providers = {
            stage: QwenTask4Provider(
                stage=stage, instruction=self.instructions[stage],
                profile_sha256=self.prompt_profile_sha,
                **config[stage + ("_provider" if stage == "response" else "_appraisal_provider")],
            ) for stage in STAGES
        }
        # Keep the canonical actor/trust preparation and the canonical validators.
        # Only substitute the underlying local HTTP provider, not another state
        # machine, appraisal implementation, response generator or retry loop.
        environment.state_updater.state_appraiser.provider.provider = providers["state"]
        environment.state_updater.interaction_appraiser.provider = providers["interaction"]
        environment.response_generator.provider = providers["response"]
        return environment


def request_providers(environment):
    return {
        "state": environment.state_updater.state_appraiser.provider,
        "interaction": environment.state_updater.interaction_appraiser.provider,
        "response": environment.response_generator.provider,
    }
