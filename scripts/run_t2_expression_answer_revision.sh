#!/usr/bin/env bash
set -euo pipefail
ROOT="/root/autodl-tmp/emotree"
OUT="$ROOT/build/t2_expression_dev_v1"
LOG="$OUT/logs/revision"
PYTHON="/root/miniconda3/bin/python"
MODEL_ROUTES="$ROOT/configs/model_routes.frontier_api.json"
mkdir -p "$LOG"
cd "$ROOT" || exit 1

: "${SOCIALFLUX_API_KEY:?Set SOCIALFLUX_API_KEY in the server environment}"

WORKERS=()
for idx in 0 1 2 3; do
  "$PYTHON" scripts/revise_t2_expression_answers.py \
    --pair-index "$idx" \
    --model-routes "$MODEL_ROUTES" \
    >"$LOG/pair${idx}.log" 2>&1 &
  WORKERS+=("$!")
done
fail=0
for pid in "${WORKERS[@]}"; do
  if ! wait "$pid"; then
    fail=$((fail + 1))
  fi
done
"$PYTHON" scripts/build_t2_expression_dev_pairs.py --summarize \
  >"$LOG/summary.log" 2>&1
exit "$fail"
