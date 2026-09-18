#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/root/autodl-tmp/emotree"
OUTPUT_ROOT="$PROJECT_ROOT/build/t2_expression_dev_v1"
LOG_ROOT="$OUTPUT_ROOT/logs"
PYTHON_BIN="/root/miniconda3/bin/python"
MODEL_ROUTES="$PROJECT_ROOT/configs/model_routes.frontier_api.json"

mkdir -p "$LOG_ROOT"
cd "$PROJECT_ROOT" || exit 1

: "${SOCIALFLUX_API_KEY:?Set SOCIALFLUX_API_KEY in the server environment}"

WORKER_PIDS=()
for spec_index in 0 1 2 3; do
  "$PYTHON_BIN" scripts/build_t2_expression_dev_pairs.py \
    --spec-index "$spec_index" \
    --model-routes "$MODEL_ROUTES" \
    >"$LOG_ROOT/pair${spec_index}.log" 2>&1 &
  WORKER_PIDS+=("$!")
done

failures=0
for pid in "${WORKER_PIDS[@]}"; do
  if ! wait "$pid"; then
    failures=$((failures + 1))
  fi
done

"$PYTHON_BIN" scripts/build_t2_expression_dev_pairs.py --summarize \
  >"$LOG_ROOT/summary.log" 2>&1
exit "$failures"
