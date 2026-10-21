"""Contracts at shared boundaries used by offline tasks and experiment CLIs."""

import ast
from copy import deepcopy
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pipeline.runtime import appraisal_route_config
from providers.base import call_count
from shared.artifacts import atomic_json, canonical_json_sha256
from tasks.T2.runtime import count_requests


ROOT = Path(__file__).resolve().parents[1]


class SharedRuntimeContractsTest(unittest.TestCase):
    def test_atomic_write_preserves_unicode_and_existing_file_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "result.json"
            atomic_json(path, {"status": "完成"})
            self.assertEqual(path.read_bytes(), '{\n  "status": "完成"\n}\n'.encode())
            before = path.read_bytes()
            with self.assertRaises(TypeError):
                atomic_json(path, {"unsupported": object()})
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_content_hash_is_order_independent_but_detects_changes(self):
        left = {"scenario_id": "场景", "state": {"trust": 4, "anger": 2}}
        right = {"state": {"anger": 2, "trust": 4}, "scenario_id": "场景"}
        self.assertEqual(canonical_json_sha256(left), canonical_json_sha256(right))
        right["state"]["trust"] = 5
        self.assertNotEqual(canonical_json_sha256(left), canonical_json_sha256(right))

    def test_pinned_appraisal_route_preserves_settings_without_mutation(self):
        route = {
            "candidates": [
                {"provider": "test", "model": "candidate", "api_key_env": "TEST_ONLY", "options": {"a": 1}},
                {"provider": "test", "model": "other"},
            ],
            "model": "parent", "stream": False, "reasoning_effort": "low", "max_tokens": 42,
        }
        for key in ("provider", "state_appraisal_provider"):
            with self.subTest(key=key):
                environment = {"provider": {"model": "unused"}, key: deepcopy(route)}
                before = deepcopy(environment)
                selected = appraisal_route_config(environment, 0)
                self.assertEqual(selected["model"], "parent")
                self.assertEqual(selected["api_key_env"], "TEST_ONLY")
                self.assertEqual(selected["max_tokens"], 42)
                self.assertEqual(selected["reasoning_effort"], "low")
                self.assertIs(selected["stream"], False)
                self.assertEqual(selected["timeout"], 600)
                self.assertEqual(selected["max_transport_attempts"], 1)
                selected["options"]["a"] = 99
                self.assertEqual(environment, before)
                with self.assertRaises(IndexError):
                    appraisal_route_config(environment, 2)

    def test_call_counter_honors_provider_wrapper_delegation(self):
        class Provider:
            _call_index = 3

        class Wrapper:
            def __getattr__(self, key):
                return getattr(Provider, key)

        self.assertEqual(call_count(Wrapper()), 3)
        self.assertEqual(call_count(object()), 0)
        self.assertEqual(call_count(type("Unset", (), {"_call_index": None})()), 0)

    def test_request_total_excludes_metadata_and_cached_total(self):
        counts = {
            "environment": {"appraisal": 5, "response": 4}, "answer": 2,
            "environment_stage_count_per_turn": 2,
            "actual_requests_include_retries": True, "total": 999,
        }
        self.assertEqual(count_requests(counts), 11)

    def test_all_offline_tasks_use_same_strict_choice_validation(self):
        for task in ("T1", "T2", "T3"):
            validate = importlib.import_module(f"tasks.{task}.answering").validate_answer
            for version in ("socialflux_offline_choice_v1", "socialflux_offline_choice_v2"):
                with self.subTest(task=task, version=version):
                    item = {"benchmark_version": version, "options": {"A": "left", "B": "right"}}
                    self.assertEqual(validate({"answer": "b"}, item), {"answer": "B"})
                    for invalid in ({"answer": "C"}, {"answer": "A", "reason": "extra"}, {}):
                        with self.assertRaises(ValueError):
                            validate(invalid, item)

    def test_domain_modules_do_not_import_cli_scripts(self):
        violations = []
        for directory in ("environment", "evaluation", "offline", "pipeline", "providers", "rollout", "scenario_design", "tasks", "web", "shared"):
            for path in (ROOT / directory).rglob("*.py"):
                relative = path.relative_to(ROOT)
                if "tests" in relative.parts or relative.as_posix() == "pipeline/cli.py":
                    continue
                for node in ast.walk(ast.parse(path.read_text())):
                    modules = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                               else [alias.name for alias in node.names] if isinstance(node, ast.Import)
                               else [])
                    if any(module.split(".")[0] == "scripts" for module in modules):
                        violations.append(f"{relative}:{node.lineno}")
        self.assertEqual(violations, [], "Domain logic must have an owner outside scripts/")

    def test_offline_import_does_not_load_historical_experiment_orchestrators(self):
        result = subprocess.run(
            [sys.executable, "-c", "import offline.choice_pipeline, sys, json; print(json.dumps(sorted(m for m in sys.modules if m.startswith('scripts.'))))"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout), [])

    def test_standalone_clis_find_shared_modules_without_pythonpath(self):
        scripts = (
            "scenario_docs.py", "finalize_multimodal_video_queue.py",
            "finalize_online_multimodal_assets.py", "run_autodl_seedance_video.py",
            "run_post_generation_gates.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            for script in scripts:
                with self.subTest(script=script):
                    result = subprocess.run(
                        [sys.executable, "-I", str(ROOT / "scripts" / script), "--help"],
                        cwd=directory, capture_output=True, text=True, timeout=15,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("usage:", result.stdout)

    def test_builder_fingerprints_change_when_shared_dependencies_change(self):
        builders = (
            ("scripts.author_t2_pair_specs", "code_fingerprint"),
            ("scripts.build_scale300_task_packages", "code_fingerprint"),
            ("scripts.build_claude150_tasks", "fingerprint"),
        )
        for name, function in builders:
            module = importlib.import_module(name)
            with self.subTest(builder=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for relative in module.FINGERPRINT_FILES:
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("original source")
                with patch.object(module, "ROOT", root):
                    fingerprint = getattr(module, function)
                    for dependency in ("shared/artifacts.py", "providers/base.py"):
                        before = fingerprint()
                        (root / dependency).write_text("changed dependency")
                        self.assertNotEqual(fingerprint(), before)


if __name__ == "__main__":
    unittest.main()
