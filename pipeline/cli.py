"""Single public command surface for the active pipeline."""

import argparse
import json
from pathlib import Path
import sys

from .constants import ROLLOUT_CONFIG, SCENARIO_ROOT, T4_CONFIG
from .flow import PipelinePreflight


COMMANDS = {
    "offline-build": "build source-grounded T1–T3 choice development questions",
    "offline-eval": "validate, call or score the unified offline choice protocol",
    "preflight": "validate the active batch, one rollout, and Fable-only routing",
    "rollout": "generate one natural rollout per approved scenario",
    "gate3": "validate Gates 1-2 and admit or reject each sole trajectory",
    "tasks": "build T1/T2/T3 from Gate-3-selected trajectories",
    "t4": "run online T4 evaluation with the shared environment",
    "audit": "evaluate the final Gate 1-4 release status",
}


def _delegate(module, argv):
    module.main(argv)


def _root_parser():
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description=(
            "Canonical versioned pipeline: gate1 -> rollout -> gate2 -> "
            "gate3 -> tasks/t4 -> gate4."
        ),
    )
    parser.add_argument("command", nargs="?", choices=tuple(COMMANDS))
    parser.epilog = "\n".join(
        f"  {command:<9} {description}"
        for command, description in COMMANDS.items()
    )
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    return parser


def _run_preflight(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline preflight")
    parser.add_argument("--scenarios", type=Path, default=SCENARIO_ROOT)
    parser.add_argument("--rollout-config", type=Path, default=ROLLOUT_CONFIG)
    parser.add_argument("--t4-config", type=Path, default=T4_CONFIG)
    args = parser.parse_args(argv)
    result = PipelinePreflight(
        args.scenarios, args.rollout_config, args.t4_config
    ).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        _root_parser().print_help()
        return
    command = argv[0]
    stage_args = argv[1:]
    if command == "offline-build":
        from scripts import build_offline_choice_dev
        _delegate(build_offline_choice_dev, stage_args)
        return
    if command == "offline-eval":
        from scripts import evaluate_offline_choice
        _delegate(evaluate_offline_choice, stage_args)
        return
    if command == "preflight":
        _run_preflight(stage_args)
        return
    if command == "rollout":
        from scripts import generate_long_rollout_pool

        _delegate(generate_long_rollout_pool, stage_args)
        return
    if command == "tasks" and "--protocol" in stage_args:
        index = stage_args.index("--protocol")
        if index + 1 >= len(stage_args) or stage_args[index+1] != "choice":
            raise ValueError("tasks --protocol currently supports choice")
        from scripts import build_offline_choice_dev
        _delegate(build_offline_choice_dev, stage_args[:index] + stage_args[index+2:])
        return
    if command == "tasks":
        from scripts import run_pipeline

        _delegate(run_pipeline, stage_args)
        return
    if command == "gate3":
        from scripts import audit_formal_rollout_pool

        _delegate(audit_formal_rollout_pool, stage_args)
        return
    if command == "t4":
        from scripts import run_t4_evaluation

        _delegate(run_t4_evaluation, stage_args)
        return
    if command == "audit":
        from scripts import run_quality_gates

        _delegate(run_quality_gates, stage_args)
        return

    _root_parser().parse_args([command])
