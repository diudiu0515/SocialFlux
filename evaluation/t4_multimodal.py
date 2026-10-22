"""Bounded API adapters and real-video policies for paired T4 experiments."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
from threading import Lock
from time import monotonic, sleep

from evaluation.t4_batch import save
from evaluation.t4_media import compact_media, provider_messages, video_blocks, extract_frames, sha_file
from policies.model_policy import ModelPolicy
from providers.factory import build_provider
from providers.structured import complete_json


class RequestBudget:
    def __init__(self, path, limit):
        self.path, self.limit, self.lock = Path(path), limit, Lock()
        self.count = json.loads(self.path.read_text())["request_count"] if self.path.exists() else 0

    def take(self):
        with self.lock:
            if self.count >= self.limit:
                raise RuntimeError("experiment API request budget exhausted")
            self.count += 1
            save(self.path, {"request_count": self.count, "limit": self.limit})


class AuditedProvider:
    def __init__(self, config, directory, budget, max_attempts=1):
        if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 3:
            raise ValueError("audited transport attempts must be between 1 and 3")
        self.max_attempts = max_attempts
        self.config, self.directory, self.budget = config, Path(directory), budget
        self.provider = build_provider(config)
        self.index = len(list(self.directory.glob("*.json")))

    def __getattr__(self, key):
        return getattr(self.provider, key)

    def reset(self):
        self.provider.reset()

    def complete(self, messages, **sampling):
        for attempt in range(self.max_attempts):
            try:
                return self._complete_once(messages, **sampling)
            except Exception as exc:
                if attempt + 1 == self.max_attempts or not transient_transport_error(str(exc)):
                    raise
                sleep(5 * (attempt + 1))

    def _complete_once(self, messages, **sampling):
        self.budget.take()
        self.index += 1
        messages = provider_messages(messages, self.config["provider"])
        record = {"messages": compact_media(messages), "sampling": sampling, "status": "started"}
        started = monotonic()
        audit_start = len(getattr(self.provider, "audit_records", []))
        path = self.directory / f"{self.index:04d}.json"
        save(path, record)
        try:
            raw = self.provider.complete(messages, **sampling)
            record.update(status="completed", raw_output=raw)
            return raw
        except Exception as exc:
            record.update(status="failed", error=str(exc))
            raise
        finally:
            record["wall_seconds"] = round(monotonic() - started, 3)
            record["response_audits"] = [
                {key: value for key, value in audit.items() if key != "request"}
                for audit in getattr(self.provider, "audit_records", [])[audit_start:]
            ]
            record["provider_metrics"] = self.provider.metrics
            save(path, record)


def transient_transport_error(error):
    """Retry unavailable transport only; never change sampling or accept truncation."""
    return any(term in error.lower() for term in (
        "the service is busy", "request could not be completed", "upstream_error",
        "timed out", "timeout", "connection reset", "remote end closed",
        "http 429", "http 500", "http 502", "http 503", "http 504",
        "unterminated string starting at",
    )) and not any(term in error.lower() for term in (
        "json/schema", "truncated", "incompatible", "invalid parameter",
    ))


def assess_run_health(rows, video_models, max_failure_fraction=0.2, require_pairs=True):
    """Gate expansion on transport reliability and real paired video exposure."""
    attempted = [r for r in rows if r["status"] != "unsupported_video_input"]
    failures = [r for r in attempted if r["status"] not in {
        "completed", "completed_without_video_exposure"}]
    fraction = len(failures) / len(attempted) if attempted else 1.0
    pairs = {}
    for name in video_models:
        text = {r["scenario_id"] for r in rows if r["model_id"] == name
                and r["condition"] == "text_only" and r["status"] == "completed"}
        video = {r["scenario_id"] for r in rows if r["model_id"] == name
                 and r["condition"] == "text_video" and r["status"] == "completed"
                 and r.get("video_delivery_count", 0) > 0}
        pairs[name] = len(text & video)
    reasons = []
    if fraction > max_failure_fraction:
        reasons.append("episode_failure_fraction_exceeded")
    if require_pairs and (not pairs or any(n < 1 for n in pairs.values())):
        reasons.append("missing_valid_pair_for_supported_video_model")
    return {"passed": not reasons, "reasons": reasons,
            "attempted": len(attempted), "failures": len(failures),
            "failure_fraction": fraction, "max_failure_fraction": max_failure_fraction,
            "matched_pairs": pairs, "require_pairs": require_pairs}


class AssetPolicy(ModelPolicy):
    def __init__(self, *args, assets, transport, audit_path, **kwargs):
        self.assets, self.transport = assets, transport
        self.audit_path = Path(audit_path)
        self.deliveries = []
        super().__init__(*args, **kwargs)

    @property
    def provenance(self):
        return {**super().provenance, "video_transport": self.transport,
                "video_delivery_observations": len(self.deliveries),
                "video_audio_included": self.transport == "native_video"}

    def _observation_media_blocks(self, media):
        if self.observation_condition == "text_only":
            return []
        result = []
        for item in media:
            asset_id = item.get("media_asset_id")
            if asset_id not in self.assets:
                raise ValueError("triggered video asset missing: " + str(asset_id))
            asset = self.assets[asset_id]
            if self.transport == "video_frames" and not asset.get("frames"):
                raise ValueError("video frames were not frozen before execution")
            result.extend(video_blocks(asset, self.transport))
            self.deliveries.append({"asset_id": asset_id, "video_sha256": asset["sha256"],
                                    "transport": self.transport, "frames": asset.get("frames", [])})
        save(self.audit_path, self.deliveries)
        return result


def prepare_controls(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    controls = []
    sequences = [("red", "green", "blue", "yellow"), ("yellow", "blue", "red", "green")]
    for index, sequence in enumerate(sequences):
        path = directory / f"control_{index}.mp4"
        if not path.exists():
            command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
            for color in sequence:
                command += ["-f", "lavfi", "-i", f"color=c={color}:s=320x240:d=1:r=24"]
            command += ["-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]",
                        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
            subprocess.run(command, check=True, timeout=60)
        controls.append({"path": str(path), "sha256": sha_file(path),
                         "frames": extract_frames(path, directory / f"frames_{index}"),
                         "expected": list(sequence)})
    return controls


def probe_model(config, directory, budget, controls):
    """A successful HTTP response is insufficient: verify two temporal controls."""
    directory = Path(directory)
    result_file = directory / "result.json"
    result = json.loads(result_file.read_text()) if result_file.exists() else {
        "native_video": [], "video_frames": [], "selected_transport": None}
    if result.get("probe_complete"):
        return result
    transports = ["native_video", "video_frames"] if config["provider"] != "anthropic" else ["video_frames"]
    for transport in transports:
        if any(not row["passed"] for row in result[transport]):
            continue
        for index, control in enumerate(controls):
            if index < len(result[transport]):
                continue
            provider = AuditedProvider({**config, "max_tokens": 4096}, directory / transport / str(index), budget)
            content = [{"type": "text", "text": 'List the four full-screen colors in their temporal order. Return JSON only: {"colors":["...","...","...","..."]}. Use lowercase English color names. Do not infer unobserved frames.'}, *video_blocks(control, transport)]
            try:
                value = complete_json(provider, [{"role": "user", "content": content}], {"temperature": 0},
                                      lambda x: x if isinstance(x, dict) and isinstance(x.get("colors"), list) else (_ for _ in ()).throw(ValueError("colors must be a list")),
                                      context="temporal video transport probe", max_attempts=1)
                row = {"passed": value["colors"] == control["expected"], "response": value, "expected": control["expected"]}
            except Exception as exc:
                row = {"passed": False, "error": str(exc)}
            result[transport].append(row)
            save(result_file, {**result, "probe_complete": False})
            if not row["passed"]:
                break
        if len(result[transport]) == 2 and all(r["passed"] for r in result[transport]):
            result["selected_transport"] = transport
            break
    result["probe_complete"] = True
    save(result_file, result)
    return result
