#!/usr/bin/env python3
"""Launch the configured local Qwen using the isolated vLLM installation."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def command(config, runtime_prefix=None):
    # Existing frozen deployments keep their original runtime until a new run
    # explicitly selects a Conda prefix. Never switch a live batch implicitly.
    prefix = Path(runtime_prefix).expanduser().resolve() if runtime_prefix else ROOT / 'build/qwen_deployment/venv'
    cmd = [str(prefix / 'bin/vllm'), 'serve', str(ROOT / config['model_path']),
           '--served-model-name', config['model'], '--host', config['host'], '--port', str(config['port']),
           '--tensor-parallel-size', str(config['tensor_parallel_size']),
           '--max-model-len', str(config['max_model_len']), '--max-num-seqs', str(config['max_num_seqs']),
           '--gpu-memory-utilization', str(config['gpu_memory_utilization']),
           '--reasoning-parser', config['reasoning_parser'], '--engram-config', json.dumps(config['engram_config']),
           '--moe-backend', 'triton', '--enforce-eager', '--language-model-only', '--disable-custom-all-reduce']
    if config['enable_expert_parallel']:
        cmd.append('--enable-expert-parallel')
    return cmd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/qwen_local_deployment.json')
    parser.add_argument('--runtime-prefix', type=Path,
                        help='Explicit Conda prefix for a new deployment; legacy frozen runtime is the default')
    parser.add_argument('--print-command', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    cmd = command(config, args.runtime_prefix)
    if args.print_command:
        import shlex
        print(shlex.join(cmd))
        return
    os.chdir(ROOT)
    cache = ROOT / 'build/qwen_deployment/cache'
    for key, subdir in [('HF_HOME', 'huggingface'), ('VLLM_CACHE_ROOT', 'vllm'), ('TRITON_CACHE_DIR', 'triton'), ('TORCHINDUCTOR_CACHE_DIR', 'torchinductor')]:
        os.environ[key] = str(cache / subdir)
    os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0,1,2,3')
    os.environ.setdefault('NCCL_P2P_DISABLE', '1')
    os.environ.setdefault('OMP_NUM_THREADS', '8')
    os.execv(cmd[0], cmd)


if __name__ == '__main__':
    main()
