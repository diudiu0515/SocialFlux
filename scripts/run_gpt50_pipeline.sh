#!/usr/bin/env bash
set -u

cd "$(dirname "$0")/.."
SOCIALFLUX_PYTHON="${SOCIALFLUX_PYTHON:-python}"
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
    --rollout-config configs/gpt50_experiment/rollout.json \
    --scenarios data/gpt50/experiment/scenario/scenarios \
    --output data/gpt50/experiment/rollouts \
    --retry-limit "$rollout_retry_limit" \
    --workers "$gpt_workers" \
    --request-budget "$request_budget" \
    --allow-unreviewed \
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

"$SOCIALFLUX_PYTHON" scripts/prepare_multimodal_video_queue.py \
  --batch-root data/gpt50/experiment \
  --scenario-root data/gpt50/experiment/scenario/scenarios \
  --rollout-root data/gpt50/experiment/rollouts \
  --config configs/multimodal_generation.json \
  --expected-count 50

"$SOCIALFLUX_PYTHON" scripts/prepare_batch_gate2.py \
  --batch-root data/gpt50/experiment \
  --scenario-root data/gpt50/experiment/scenario/scenarios \
  --rollout-root data/gpt50/experiment/rollouts \
  --rollout-config configs/gpt50_experiment/rollout.json \
  --scenario-limit 10 \
  --allow-pending-video
