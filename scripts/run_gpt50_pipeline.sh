#!/usr/bin/env bash
set -u

cd "$(dirname "$0")/.."
SOCIALFLUX_PYTHON="${SOCIALFLUX_PYTHON:-python}"
scenario_root="data/gpt50/experiment/scenario/scenarios_state_v3"
rollout_root="data/gpt50/experiment/rollouts_state_v328_restored"
rollout_config="configs/gpt50_experiment/rollout.state_v3.json"
review_registry="${GPT50_STATE_V3_REVIEW_REGISTRY:-$scenario_root/human_review/scenario_state_review.signed.json}"
if [ ! -f "$review_registry" ]; then
  echo "GPT50 state-v3 rollout is blocked: missing human-signed registry $review_registry"
  exit 3
fi
"$SOCIALFLUX_PYTHON" scripts/check_rollout_readiness.py \
  --scenarios "$scenario_root" \
  --rollout-config "$rollout_config" \
  --require-human-frozen || exit 3
gpt_workers="${GPT50_WORKERS_INITIAL:-4}"
gpt_workers_min="${GPT50_WORKERS_MIN:-2}"
rollout_passes_max="${GPT50_ROLLOUT_PASSES_MAX:-1}"
rollout_retry_limit="${GPT50_ROLLOUT_RETRY_LIMIT:-1}"
request_budget="${GPT50_REQUEST_BUDGET:-18000}"
retry_cooldown=10

rollout_pass=0
rollout_ready=false
while [ "$rollout_pass" -lt "$rollout_passes_max" ]; do
  rollout_pass=$((rollout_pass + 1))
  if "$SOCIALFLUX_PYTHON" scripts/generate_long_rollout_pool.py \
    --rollout-config "$rollout_config" \
    --scenarios "$scenario_root" \
    --output "$rollout_root" \
    --retry-limit "$rollout_retry_limit" \
    --workers "$gpt_workers" \
    --request-budget "$request_budget" \
    --review-registry "$review_registry" \
    --development-role-partition \
    --resume \
    --allow-route-migration; then
    rollout_ready=true
    break
  fi
  if [ "$gpt_workers" -gt "$gpt_workers_min" ]; then
    gpt_workers=$((gpt_workers - 1))
  fi
  if [ "$rollout_pass" -lt "$rollout_passes_max" ]; then
    sleep "$retry_cooldown"
    if [ "$retry_cooldown" -lt 120 ]; then
      retry_cooldown=$((retry_cooldown * 2))
    fi
  fi
done
if [ "$rollout_ready" != true ]; then
  exit 2
fi

if [ "${GPT50_STATE_V3_RUN_DOWNSTREAM:-0}" != "1" ]; then
  echo "GPT50 state-v3 rollout finished; downstream Gate/video preparation remains disabled"
  exit 0
fi

"$SOCIALFLUX_PYTHON" scripts/prepare_multimodal_video_queue.py \
  --batch-root data/gpt50/experiment \
  --scenario-root "$scenario_root" \
  --rollout-root "$rollout_root" \
  --config configs/multimodal_generation.json \
  --expected-count 50 \
  --model-routes configs/gpt50_experiment/model_routes.astra.json \
  --translation-workers "$gpt_workers"

"$SOCIALFLUX_PYTHON" scripts/prepare_batch_gate2.py \
  --batch-root data/gpt50/experiment \
  --scenario-root "$scenario_root" \
  --rollout-root "$rollout_root" \
  --rollout-config "$rollout_config" \
  --scenario-limit 10 \
  --allow-pending-video
