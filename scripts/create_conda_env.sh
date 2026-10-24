#!/usr/bin/env bash
# Create a new, isolated environment; never update a running experiment in place.
set -euo pipefail

profile="${1:-core}"
mode="${2:-}"
if [[ "$profile" == "--help" || "$profile" == "-h" ]]; then
  echo 'Usage: bash scripts/create_conda_env.sh [core|qwen] [--dry-run]'
  echo 'SOCIALFLUX_STORAGE_ROOT selects the data-disk directory (default: build/runtime).'
  exit 0
fi
if [[ $# -gt 2 || ( -n "$mode" && "$mode" != "--dry-run" ) ]]; then
  echo 'Expected [core|qwen] [--dry-run]' >&2
  exit 2
fi
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
case "$profile" in
  core) definition="$project_root/environment.yml" ;;
  qwen) definition="$project_root/environments/qwen.yml" ;;
  *) echo 'Unknown profile; expected core or qwen' >&2; exit 2 ;;
esac
storage="${SOCIALFLUX_STORAGE_ROOT:-$project_root/build/runtime}"
if [[ "$storage" != /* || "$storage" == / ]]; then
  echo 'SOCIALFLUX_STORAGE_ROOT must be an absolute data-disk directory.' >&2
  exit 2
fi
prefix="$storage/envs/$profile"
conda_exe="${CONDA_EXE:-conda}"
if [[ -e "$prefix" ]]; then
  echo "Refusing to overwrite an existing environment: $prefix" >&2
  echo 'Activate it, or select a new SOCIALFLUX_STORAGE_ROOT for a new run.' >&2
  exit 1
fi
command=("$conda_exe" env create --prefix "$prefix" --file "$definition" --yes)
if [[ "$mode" == '--dry-run' ]]; then
  printf 'Environment: %s\nCache and temporary storage: %s\n' "$prefix" "$storage"
  printf '%q ' "${command[@]}"
  printf '\n'
  exit 0
fi
mkdir -p "$storage/cache/conda" "$storage/cache/pip" "$storage/tmp"
export CONDA_PKGS_DIRS="$storage/cache/conda"
export PIP_CACHE_DIR="$storage/cache/pip"
export TMPDIR="$storage/tmp"
# Conda passes pip requirement paths relative to the environment definition.
cd "$project_root"
"${command[@]}"
"$conda_exe" env config vars set --prefix "$prefix" \
  "CONDA_PKGS_DIRS=$storage/cache/conda" \
  "PIP_CACHE_DIR=$storage/cache/pip" \
  "UV_CACHE_DIR=$storage/cache/uv" \
  "npm_config_cache=$storage/cache/npm" \
  "XDG_CACHE_HOME=$storage/cache" \
  "HF_HOME=$storage/cache/huggingface" \
  "TRITON_CACHE_DIR=$storage/cache/triton" \
  "VLLM_CACHE_ROOT=$storage/cache/vllm" \
  "TMPDIR=$storage/tmp"
"$conda_exe" run --prefix "$prefix" python -m pip check
mkdir -p "$storage/locks/$profile"
"$conda_exe" list --prefix "$prefix" --explicit > "$storage/locks/$profile/conda-explicit.txt"
"$conda_exe" run --prefix "$prefix" python -m pip freeze > "$storage/locks/$profile/pip-freeze.txt"
printf '\nActivate with: conda activate %q\n' "$prefix"
printf 'Resolved package inventories: %s/locks/%s\n' "$storage" "$profile"
