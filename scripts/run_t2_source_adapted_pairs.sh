#!/usr/bin/env bash
set -euo pipefail

project_root="/root/autodl-tmp/emotree"
run_id="${1:-run_$(date -u +%Y%m%dT%H%M%SZ)}"
config_path="${2:-$project_root/build/t2_pair_specs/runtime_config.json}"
workers="${T2_WORKERS:-4}"
request_budget="${T2_REQUEST_BUDGET:-6000}"

cd "$project_root"
python -m pipeline preflight
python scripts/build_t2_source_adapted_pairs.py \
  --config "$config_path" \
  --output build/t2_source_adapted \
  --run-id "$run_id" \
  --all \
  --workers "$workers" \
  --request-budget "$request_budget" \
  --skip-existing
