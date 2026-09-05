#!/usr/bin/env python3
"""Generate and audit EchoMimicV2 talking-head assets."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / ".local_tools" / "echomimic_v2"
MODEL = ROOT / ".local_models" / "EchoMimicV2"
ENV_PYTHON = ROOT / ".local_models" / "echomimic-env" / "bin" / "python"
MEDIA = ROOT / "media" / "talking_head"
MANIFEST = MEDIA / "manifest.json"
BUILD = ROOT / "build" / "talking_head"
POSES = TOOL / "assets" / "halfbody_demo" / "pose"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(asset_id):
    return asset_id.replace("--", "__").replace("/", "_")


def pose_for(record):
    line = record["utterance"]
    if "不能再拖" in line:
        return POSES / "02"
    if "一点时间" in line:
        return POSES / "03"
    return POSES / "01"


def model_config(test_cases):
    return {
        "pretrained_base_model_path": str(MODEL / "sd-image-variations-diffusers"),
        "pretrained_vae_path": str(MODEL / "sd-vae-ft-mse"),
        "denoising_unet_path": str(MODEL / "denoising_unet_acc.pth"),
        "reference_unet_path": str(MODEL / "reference_unet.pth"),
        "pose_encoder_path": str(MODEL / "pose_encoder.pth"),
        "motion_module_path": str(MODEL / "motion_module_acc.pth"),
        "audio_model_path": str(MODEL / "audio_processor" / "tiny.pt"),
        "inference_config": str(TOOL / "configs" / "inference" / "inference_v2.yaml"),
        "weight_dtype": "fp16",
        "test_cases": test_cases,
    }


def prepare_configs():
    manifest = load(MANIFEST)
    inputs = BUILD / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    shards = [[] for _ in range(4)]
    for index, record in enumerate(manifest["assets"]):
        shards[index % 4].append(record)
    for shard_id, records in enumerate(shards):
        # EchoMimicV2's upstream accelerated runner mutates args.L after each
        # case. Process longer clips first so a shorter clip cannot cap a
        # later one in the same model-loading session.
        records.sort(key=lambda item: item["duration_seconds"], reverse=True)
        cases = {}
        for record in records:
            name = safe_name(record["asset_id"])
            reference = ROOT / record["reference_path"]
            audio = ROOT / record["audio_path"]
            copied_reference = inputs / f"{name}.png"
            copied_audio = inputs / f"{name}.wav"
            shutil.copy2(reference, copied_reference)
            shutil.copy2(audio, copied_audio)
            cases[str(copied_reference)] = [
                str(copied_audio),
                str(pose_for(record)),
            ]
        dump(BUILD / f"shard_{shard_id}.json", model_config(cases))
    print(json.dumps({"shards": 4, "assets": len(manifest["assets"])}))


def required_paths():
    return [
        TOOL / "infer_acc.py",
        MODEL / "denoising_unet_acc.pth",
        MODEL / "reference_unet.pth",
        MODEL / "pose_encoder.pth",
        MODEL / "motion_module_acc.pth",
        MODEL / "audio_processor" / "tiny.pt",
        MODEL / "sd-image-variations-diffusers" / "unet" / "diffusion_pytorch_model.bin",
        MODEL / "sd-vae-ft-mse" / "diffusion_pytorch_model.safetensors",
        ENV_PYTHON,
    ]


def run_shard(shard_id):
    missing = [str(path) for path in required_paths() if not path.exists()]
    if missing:
        raise FileNotFoundError("missing EchoMimicV2 dependencies: " + ", ".join(missing))
    run_dir = BUILD / "runs" / f"shard_{shard_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = str(shard_id)
    env["FFMPEG_PATH"] = str(Path(shutil.which("ffmpeg")).parent)
    command = [
        str(ENV_PYTHON),
        str(TOOL / "infer_acc.py"),
        "--config", str(BUILD / f"shard_{shard_id}.json"),
        "-W", "768", "-H", "768", "-L", "120",
        "--steps", "6", "--fps", "24",
        "--seed", str(420 + shard_id),
    ]
    subprocess.run(command, cwd=run_dir, env=env, check=True)


def probe(path):
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height",
        "-of", "json", str(path),
    ], text=True)
    data = json.loads(raw)
    video = next(
        (item for item in data["streams"] if item["codec_type"] == "video"),
        {},
    )
    kinds = {item["codec_type"] for item in data["streams"]}
    return {
        "duration_seconds_actual": round(float(data["format"]["duration"]), 3),
        "width": video.get("width"),
        "height": video.get("height"),
        "has_video": "video" in kinds,
        "has_audio": "audio" in kinds,
    }


def find_generated(record):
    name = safe_name(record["asset_id"])
    matches = sorted((BUILD / "runs").glob(f"shard_*/output/**/{name}-a-{name}-i0_sig.mp4"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected one generated output for {record['asset_id']}, found {len(matches)}"
        )
    return matches[0]


def update_scenarios(records):
    by_scenario = {}
    for record in records:
        by_scenario.setdefault(record["scenario_id"], {})[
            record["trigger_label"]
        ] = record
    for scenario_path in sorted(
        (ROOT / "configs" / "scenarios").glob("scenario_*/scenario_*.json")
    ):
        scenario = load(scenario_path)
        matched = by_scenario.get(scenario["scenario_id"], {})
        for trigger in scenario.get("video_triggers", []):
            record = matched.get(trigger["trigger_id"])
            trigger["media_asset_id"] = (
                record["asset_id"] if record and record["status"] == "generated" else None
            )
        generated = sum(
            trigger.get("media_asset_id") is not None
            for trigger in scenario.get("video_triggers", [])
        )
        total = len(scenario.get("video_triggers", []))
        scenario["media_generation"]["asset_status"] = (
            "generated" if total and generated == total else "partial"
        )
        scenario["media_generation"]["provider"] = "BadToBest/EchoMimicV2"
        dump(scenario_path, scenario)


def collect():
    manifest = load(MANIFEST)
    errors = []
    for record in manifest["assets"]:
        source = find_generated(record)
        target = ROOT / record["video_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        result = probe(target)
        duration_matches = abs(
            result["duration_seconds_actual"] - float(record["duration_seconds"])
        ) <= 0.25
        result["duration_matches_request"] = duration_matches
        if (
            not result["has_video"]
            or not result["has_audio"]
            or not 3 <= result["duration_seconds_actual"] <= 8
            or not duration_matches
        ):
            errors.append({"asset_id": record["asset_id"], **result})
            record["status"] = "failed_validation"
            continue
        record.update(result)
        record["video_sha256"] = file_sha256(target)
        record["status"] = "generated"
    manifest["generated_count"] = sum(
        item["status"] == "generated" for item in manifest["assets"]
    )
    manifest["validation_errors"] = errors
    dump(MANIFEST, manifest)
    update_scenarios(manifest["assets"])
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scenario_docs.py")],
        cwd=ROOT,
        check=True,
    )
    print(json.dumps({
        "generated": manifest["generated_count"],
        "errors": errors,
    }, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run-shard", type=int, choices=range(4))
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare_configs()
    elif args.run_shard is not None:
        run_shard(args.run_shard)
    elif args.collect:
        collect()
    else:
        parser.error("choose --prepare, --run-shard, or --collect")


if __name__ == "__main__":
    main()
