"""Resume transport-failed Gate probes with exact completed API-call reuse.

Successful intervention construction and appraisal responses are replayed from
their request hashes. Only missing outputs call the provider again; an error is
not a reason to sample a different intervention or natural trajectory.
"""
import argparse
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor, as_completed

from offline import provider_compat
from offline.choice_builder import load, save, sha
from offline.reuse_audit import digest
from offline.oracle import now
from scripts import complete_gate_machine_checks as checks
from web.live_rollouts import ROOT

OriginalLoggedProvider = provider_compat.OfflineLoggedProvider


class ReuseCompletedCalls:
    def __init__(self, provider, directory):
        self.directory = Path(directory)
        self.provider = OriginalLoggedProvider(provider, directory)
        self.cache = {}
        for path in sorted(self.directory.glob("*.json"), key=lambda p: load(p).get("started_at_unix", 0)):
            record = load(path)
            if record.get("status") == "completed" and "raw_output" in record:
                key = digest({"messages": record["messages"], "generation": record["generation"]})
                self.cache.setdefault(key, (path, record["raw_output"]))
        cursor = provider
        seen = set()
        while cursor is not None and id(cursor) not in seen:
            seen.add(id(cursor))
            if "timeout" in vars(cursor):
                cursor.timeout = max(cursor.timeout, 180)
            cursor = vars(cursor).get("provider")

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def complete(self, messages, **generation):
        key = digest({"messages": messages, "generation": generation})
        if key in self.cache:
            source, raw = self.cache[key]
            save(self.directory / "reuse" / (uuid4().hex + ".json"),
                 {"request_sha256": key, "original_call": str(source.relative_to(ROOT)),
                  "original_call_sha256": sha(source), "at": now(), "new_network_request": False})
            # State appraisers record the actor-bound wire request inside the
            # provider stack. Re-enter that transformation, but replace only its
            # network leaf with the frozen output so its audit list is populated.
            cursor = self.provider.provider
            seen = set()
            while cursor is not None and id(cursor) not in seen:
                seen.add(id(cursor))
                if type(cursor).__name__ in ("_UnifiedStateProvider", "_ActorBindingProvider"):
                    inner = cursor.provider
                    class FrozenOutput:
                        def __getattr__(self, name):
                            return getattr(inner, name)
                        def complete(self, messages, **kwargs):
                            return raw
                    with patch.object(cursor, "provider", FrozenOutput()):
                        return self.provider.provider.complete(messages, **generation)
                cursor = vars(cursor).get("provider")
            return raw
        return self.provider.complete(messages, **generation)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="data/gate2_machine_20261020_complete")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    run = ROOT / args.run
    plans, config = checks.materialize(run)
    scenarios = {p["case"]["scenario_id"]: p["scenario"] for p in plans}
    trajectories = {t["scenario_id"]: t for t in checks.probes.load_records(run / "rollouts")}
    selected = []
    for kind, error_key in (("probes", "error"), ("backbone", "replay_errors")):
        for path in sorted((run / kind).glob("*/result.json")):
            record = load(path)
            if not record["record"].get(error_key):
                continue
            # One bounded continuation for a transport-failed experiment.
            marker = path.with_name("transport_continuation.json")
            previous = load(marker) if marker.exists() else {}
            if previous and (previous.get("attempt", 1) >= 2 or previous.get("status") == "running"):
                continue
            errors = str(record["record"].get(error_key))
            if not any(term in errors for term in ("TimeoutError", "timed out", "429", "HTTPError", "Connection", "URLError", "IndexError")):
                continue
            archive = path.with_name("result.before_transport_continuation.json")
            if not archive.exists():
                save(archive, record)
            else:
                save(path.with_name("result.before_transport_continuation_2.json"), record)
            save(marker, {"at": now(), "script_sha256": sha(Path(__file__)),
                          "source_result_sha256": sha(path), "reuse_policy": "exact_completed_request_hashes",
                          "transport_timeout_seconds": 180, "attempt": previous.get("attempt", 0) + 1,
                          "previous_continuation": previous or None, "status": "running"})
            path.unlink()
            selected.append((kind, path.parent.name, marker))
    replay = checks.Replay(plans, run / "replay")
    specs = load(run / "gate2/backbone_config.runtime.json")["backbones"]
    def job(kind, sid, marker):
        if kind == "probes":
            result = checks.intervention_job(trajectories[sid], scenarios, config, replay, run)
        else:
            result = checks.backbone_job(trajectories[sid], scenarios[sid], replay, specs, run)
        prior = load(marker)
        save(marker, {**prior, "status": "executed", "completed_at": now(),
                      "still_failed": bool(result.get("error") or result.get("replay_errors"))})
        return result
    with patch.object(checks, "OfflineLoggedProvider", ReuseCompletedCalls), \
         patch.object(provider_compat, "OfflineLoggedProvider", ReuseCompletedCalls), \
         patch.object(checks.probes, "ModelEnvironmentFactory", replay.factory), \
         patch.object(checks.probes, "_replay", replay.replay):
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(job, *row): row for row in selected}
            for future in as_completed(futures):
                kind, sid, marker = futures[future]
                try:
                    result = future.result()
                    print(kind, sid, "error" if result.get("error") or result.get("replay_errors") else "completed", flush=True)
                except Exception as exc:
                    save(marker.with_name("continuation_failure.json"), {"type": type(exc).__name__, "error": str(exc)})
                    # Retain a materialized failure in aggregate coverage.
                    if not marker.with_name("result.json").exists():
                        save(marker.with_name("result.json"), load(marker.with_name("result.before_transport_continuation.json")))
                    print(kind, sid, "FAILED", str(exc)[:180], flush=True)
                checks.aggregate_gate2(run, list(trajectories.values()),
                                       load(run / "reused_interventions.json")["records"], specs, plans)


if __name__ == "__main__":
    main()
