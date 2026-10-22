#!/usr/bin/env python3
"""Generate, validate, and install local MuseTalk 1.5 talking-head assets."""

import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / ".local_tools" / "musetalk"
ENV_PYTHON = ROOT / ".local_models" / "musetalk-env" / "bin" / "python"
MEDIA = ROOT / "media" / "talking_head"
MANIFEST = MEDIA / "manifest.json"
BUILD = ROOT / "build" / "talking_head"
RUNS = BUILD / "musetalk_runs"
BACKUP = BUILD / "backup_echomimic_multimodel_v2_assets"
SHARD_COUNT = 4


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


def prepare_configs():
    manifest = load(MANIFEST)
    shards = [[] for _ in range(SHARD_COUNT)]
    for index, record in enumerate(manifest["assets"]):
        shards[index % SHARD_COUNT].append(record)
    for shard_id, records in enumerate(shards):
        tasks = {}
        for index, record in enumerate(records):
            tasks[f"asset_{index:02d}"] = {
                "video_path": str(ROOT / record["reference_path"]),
                "audio_path": str(ROOT / record["audio_path"]),
                "result_name": f"{safe_name(record['asset_id'])}.mp4",
            }
        dump(BUILD / f"musetalk_shard_{shard_id}.yaml", tasks)
    print(json.dumps({"shards": SHARD_COUNT, "assets": len(manifest["assets"])}))


def required_paths():
    return [
        TOOL / "scripts" / "inference.py",
        TOOL / "models" / "musetalkV15" / "unet.pth",
        TOOL / "models" / "musetalkV15" / "musetalk.json",
        TOOL / "models" / "whisper" / "pytorch_model.bin",
        TOOL / "models" / "sd-vae" / "diffusion_pytorch_model.safetensors",
        TOOL / "models" / "face-parse-bisent" / "79999_iter.pth",
        ENV_PYTHON,
    ]


def run_shard(shard_id):
    missing = [str(path) for path in required_paths() if not path.exists()]
    if missing:
        raise FileNotFoundError("missing MuseTalk dependencies: " + ", ".join(missing))
    run_dir = RUNS / f"shard_{shard_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = str(shard_id)
    command = [
        str(ENV_PYTHON), "-m", "scripts.inference",
        "--inference_config", str(BUILD / f"musetalk_shard_{shard_id}.yaml"),
        "--result_dir", str(run_dir),
        "--unet_model_path", "models/musetalkV15/unet.pth",
        "--unet_config", "models/musetalkV15/musetalk.json",
        "--version", "v15",
        "--fps", "25",
        "--batch_size", "16",
        "--gpu_id", "0",
    ]
    subprocess.run(command, cwd=TOOL, env=env, check=True)


def probe(path):
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries",
        (
            "format=duration:stream=codec_type,codec_name,width,height,"
            "r_frame_rate,pix_fmt,sample_rate,channels"
        ),
        "-of", "json", str(path),
    ], text=True)
    data = json.loads(raw)
    video = next(
        (item for item in data["streams"] if item["codec_type"] == "video"),
        {},
    )
    audio = next(
        (item for item in data["streams"] if item["codec_type"] == "audio"),
        {},
    )
    kinds = {item["codec_type"] for item in data["streams"]}
    return {
        "duration_seconds_actual": round(float(data["format"]["duration"]), 3),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": round(float(Fraction(video.get("r_frame_rate", "0/1"))), 3),
        "video_codec": video.get("codec_name"),
        "pixel_format": video.get("pix_fmt"),
        "audio_codec": audio.get("codec_name"),
        "audio_sample_rate": int(audio.get("sample_rate", 0)),
        "audio_channels": audio.get("channels"),
        "has_video": "video" in kinds,
        "has_audio": "audio" in kinds,
    }


def find_generated(record):
    name = f"{safe_name(record['asset_id'])}.mp4"
    matches = sorted(RUNS.glob(f"shard_*/v15/{name}"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected one output for {record['asset_id']}, found {len(matches)}"
        )
    return matches[0]


def backup_existing(record):
    source = ROOT / record["video_path"]
    target = BACKUP / Path(record["video_path"]).relative_to("media/talking_head")
    if source.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


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
        scenario["media_generation"]["provider"] = "TMElyralab/MuseTalk 1.5 (local)"
        dump(scenario_path, scenario)


def collect():
    manifest = load(MANIFEST)
    errors = []
    for record in manifest["assets"]:
        source = find_generated(record)
        target = ROOT / record["video_path"]
        backup_existing(record)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        result = probe(target)
        duration_matches = abs(
            result["duration_seconds_actual"] - float(record["duration_seconds"])
        ) <= 0.25
        result["duration_matches_request"] = duration_matches
        valid = (
            result["has_video"]
            and result["has_audio"]
            and 3 <= result["duration_seconds_actual"] <= 8
            and duration_matches
            and result["width"] >= 512
            and result["height"] >= 512
            and result["fps"] == 25
            and result["video_codec"] == "h264"
            and result["pixel_format"] == "yuv420p"
        )
        if not valid:
            errors.append({"asset_id": record["asset_id"], **result})
            record["status"] = "failed_validation"
            continue
        record.update(result)
        record.update({
            "provider": "TMElyralab/MuseTalk 1.5",
            "provider_license": "MIT",
            "generation_profile": "multimodel_v4_natural_speech_musetalk_v15",
            "audio_sha256": file_sha256(ROOT / record["audio_path"]),
            "audio_duration_seconds": result["duration_seconds_actual"],
            "video_sha256": file_sha256(target),
            "quality_status": "structural_pass_av_and_visual_review_pending",
            "quality_checks": {
                "gate_1_media_structure": "pass",
                "gate_2_audio_conditioned_lipsync": "pending_av_screen",
                "gate_3_identity_and_visual_stability": "pending_visual_screen",
                "gate_4_website_manifest_integrity": "pending_web_check",
                "duration_3_to_8_seconds": True,
                "audio_video_streams_present": True,
                "human_lipsync_and_realism_review": "pending",
            },
            "status": "generated",
        })
    manifest.update({
        "generator": "TMElyralab/MuseTalk 1.5",
        "generation_profile": "multimodel_v4_natural_speech_musetalk_v15",
        "generated_count": sum(
            item["status"] == "generated" for item in manifest["assets"]
        ),
        "validation_errors": errors,
        "structural_validation": "passed" if not errors else "failed",
    })
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
    parser.add_argument("--run-shard", type=int, choices=range(SHARD_COUNT))
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare_configs()
    elif args.run_shard is not None:
        run_shard(args.run_shard)
    elif args.collect:
        collect()
    else:
        parser.error("select --prepare, --run-shard, or --collect")


if __name__ == "__main__":
    main()
