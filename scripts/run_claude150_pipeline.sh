#!/usr/bin/env bash
set -u

cd "$(dirname "$0")/.."
claude150_pause_file="${CLAUDE150_PAUSE_FILE:-data/runtime/claude150.pause}"
if [ -e "$claude150_pause_file" ]; then
  echo "Claude150 rollout is paused by $claude150_pause_file"
  exit 0
fi
SOCIALFLUX_PYTHON="${SOCIALFLUX_PYTHON:-python}"
scenario_root="data/claude150_v1/scenarios_state_v3"
rollout_root="data/claude150_v1/rollouts_state_v328_restored"
rollout_config="configs/claude150_v1/rollout.state_v3.json"
review_registry="${CLAUDE150_STATE_V3_REVIEW_REGISTRY:-$scenario_root/human_review/scenario_state_review.signed.json}"
if [ ! -f "$review_registry" ]; then
  echo "Claude150 state-v3 rollout is blocked: missing human-signed registry $review_registry"
  exit 3
fi
"$SOCIALFLUX_PYTHON" scripts/check_rollout_readiness.py \
  --scenarios "$scenario_root" \
  --rollout-config "$rollout_config" \
  --require-human-frozen || exit 3

refresh_status() {
  "$SOCIALFLUX_PYTHON" scripts/audit_active_batch.py \
    --batch-root data/claude150_v1 \
    --expected-count 150 \
    --scenario-id-prefix CF150_ \
    >/dev/null 2>&1 || true
}

pipeline_passes_max="${CLAUDE150_PIPELINE_PASSES_MAX:-1}"
pipeline_pass=0
pipeline_ready=false
while [ "$pipeline_pass" -lt "$pipeline_passes_max" ]; do
  pipeline_pass=$((pipeline_pass + 1))
  if "$SOCIALFLUX_PYTHON" scripts/run_claude150_full.py \
    --batch-root data/claude150_v1 \
    --model-routes configs/claude150_v1/model_routes.chat.pool2.json \
    --rollout-config "$rollout_config" \
    --scenario-root "$scenario_root" \
    --rollout-root "$rollout_root" \
    --review-registry "$review_registry" \
    --count 150 \
    --scenario-workers 1 \
    --rollout-workers 2 \
    --task-workers 2 \
    --max-attempts 1 \
    --allow-route-migration \
    --stage-retries 0 \
    --stage-retry-cooldown 10 \
    --from-stage rollouts \
    --through-stage rollouts; then
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
echo "Claude150 state-v3 rollout finished; downstream Gate/video stages remain disabled"
