"""Frozen constants for the active Scale300/Fable production path."""

from pathlib import Path


ACTIVE_MODEL = "claude-fable-5"
SCENARIO_COUNT = 300
SEEDS_PER_SCENARIO = 3
MAX_TURNS = 20
MIN_MAIN_TURNS = 10

SCENARIO_ROOT = Path("configs/scale300_v1/scenarios")
ROLLOUT_CONFIG = Path("configs/formal_rollout_pool.json")
MODEL_ROUTES = Path("configs/model_routes.frontier_api.json")
REVIEW_CONFIG = Path("configs/review_models.json")
T2_CONFIG = Path("configs/t2_source_adaptation_v2.json")
T4_CONFIG = Path("configs/t4_evaluation.json")

APPRAISAL_PROMPT = "environment_appraisal_v11"
RESPONSE_PROMPT = "environment_response_v25"
POLICY_PROMPT = "task_t4_action_v21"
T4_JUDGE_PROMPT = "t4_judge_v2"
