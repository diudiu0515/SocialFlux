#!/usr/bin/env bash
set -u

cd "$(dirname "$0")/.."
SOCIALFLUX_PYTHON="${SOCIALFLUX_PYTHON:-python}"
scenario_workers="${CLAUDE150_SCENARIO_WORKERS_INITIAL:-2}"
scenario_workers_min="${CLAUDE150_SCENARIO_WORKERS_MIN:-2}"
scenario_passes_max="${CLAUDE150_SCENARIO_PASSES_MAX:-1}"
scenario_max_attempts="${CLAUDE150_SCENARIO_MAX_ATTEMPTS:-1}"
retry_cooldown=10

refresh_status() {
  "$SOCIALFLUX_PYTHON" scripts/audit_active_batch.py \
    --batch-root data/claude150_v1 \
    --expected-count 150 \
    --scenario-id-prefix CF150_ \
    >/dev/null 2>&1 || true
}

scenario_pass=0
scenario_ready=false
while [ "$scenario_pass" -lt "$scenario_passes_max" ]; do
  scenario_pass=$((scenario_pass + 1))
  if "$SOCIALFLUX_PYTHON" scripts/generate_claude150_scenarios.py \
    --output data/claude150_v1 \
    --model-routes configs/claude150_v1/model_routes.chat.pool2.json \
    --count 150 \
    --workers "$scenario_workers" \
    --max-attempts "$scenario_max_attempts" \
    --seed 915000 \
    --scenarios-only \
    --resume \
    --allow-route-migration \
    --allow-prompt-migration; then
    refresh_status
    scenario_ready=true
    break
  fi
  refresh_status
  if [ "$scenario_workers" -gt "$scenario_workers_min" ]; then
    scenario_workers=$((scenario_workers - 1))
  fi
  if [ "$scenario_pass" -lt "$scenario_passes_max" ]; then
    sleep "$retry_cooldown"
    if [ "$retry_cooldown" -lt 120 ]; then
      retry_cooldown=$((retry_cooldown * 2))
    fi
  fi
done
if [ "$scenario_ready" != true ]; then
  exit 2
fi

pipeline_passes_max="${CLAUDE150_PIPELINE_PASSES_MAX:-1}"
pipeline_pass=0
pipeline_ready=false
while [ "$pipeline_pass" -lt "$pipeline_passes_max" ]; do
  pipeline_pass=$((pipeline_pass + 1))
  if "$SOCIALFLUX_PYTHON" scripts/run_claude150_full.py \
    --batch-root data/claude150_v1 \
    --model-routes configs/claude150_v1/model_routes.chat.pool2.json \
    --rollout-config configs/claude150_v1/rollout.json \
    --count 150 \
    --scenario-workers 1 \
    --rollout-workers 2 \
    --task-workers 2 \
    --max-attempts 1 \
    --allow-route-migration \
    --stage-retries 0 \
    --stage-retry-cooldown 10 \
    --from-stage rollouts; then
    pipeline_ready=true
    break
  fi
  if [ "$pipeline_pass" -lt "$pipeline_passes_max" ]; then
    sleep 30
  fi
done
if [ "$pipeline_ready" != true ]; then
  refresh_status
  exit 2
fi

"$SOCIALFLUX_PYTHON" scripts/prepare_batch_gate2.py \
  --batch-root data/claude150_v1 \
  --scenario-root data/claude150_v1/scenarios \
  --rollout-root data/claude150_v1/rollouts \
  --rollout-config configs/claude150_v1/rollout.json \
  --scenario-limit 10 \
  --allow-pending-video
refresh_status
