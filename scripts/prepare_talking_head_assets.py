#!/usr/bin/env python3
"""Prepare safe talking-head requests and speech assets."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scenario_design.catalog import discover_scenario_paths

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "configs" / "scenarios"
MEDIA = ROOT / "media" / "talking_head"
ASSETS = MEDIA / "assets"
REQUESTS = MEDIA / "requests"
MANIFEST = MEDIA / "manifest.json"
VOICE_PROFILES = ROOT / "configs" / "talking_head_voice_profiles.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def media_probe(path):
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    ], text=True)
    return round(float(raw.strip()), 3)


def motion_profile(expression):
    text = " ".join(str(value) for value in expression.values())
    if any(word in text for word in ("骤然", "迅速", "收紧", "前倾", "急促", "加快")):
        return "reactive"
    if any(word in text for word in ("移开", "回避", "低头", "后撤", "动作减少")):
        return "withdrawn"
    return "measured"


def prompt_for(scenario, trigger, line):
    expression = trigger["observable_expression"]
    cues = "；".join(expression.get("behavioral_cues", []))
    role = scenario["environment_agent"]["persona"].get("role", "对话者")
    return (
        "写实纪录片质感中近景，固定机位，单人出镜，保持参考肖像身份、年龄、服装与背景一致。"
        f"角色是{role}，自然地说普通话，完整台词是：‘{line}’"
        f"面部：{expression.get('facial_expression', '自然克制')}；"
        f"视线：{expression.get('gaze', '自然注视')}；"
        f"头部：{expression.get('head_motion', '轻微自然头部动作')}；"
        f"反应时机：{expression.get('response_timing', '自然停顿后回应')}；"
        f"说话方式：{expression.get('speech_style', '正常语速')}；"
        f"韵律：{expression.get('prosody', '克制')}；"
        f"动作：{cues or '轻微自然头部动作'}。"
        "普通话音素与唇形逐字同步，静音处自然闭唇；眨眼、呼吸和微表情连续，"
        "牙齿与面部边缘稳定，不夸张，不切镜，无字幕、标签、水印或其他人物。"
    )


def _signed(value, suffix):
    return f"{int(value):+d}{suffix}"


def prosody_controls(trigger, profile):
    expression = trigger.get("observable_expression", {})
    trigger_id = trigger.get("trigger_id", "").lower()
    style_text = " ".join([
        expression.get("speech_style", ""),
        expression.get("prosody", ""),
    ]).lower()
    urgent_ids = (
        "escalation", "alarm", "shock", "defensive", "microcontrol",
        "overload", "confrontation", "shutdown", "lock", "guard",
    )
    opening_ids = (
        "relief", "reconsideration", "recognized", "reassessment",
        "opens", "lands", "coalition", "acknowledged", "doubt", "shift",
        "curiosity", "reengagement",
    )
    quiet_ids = (
        "withdrawal", "grief", "rupture", "hesitant", "guilt", "wound",
    )
    rate_adjustment = 0
    pitch_adjustment = 0
    volume_adjustment = 0
    profile_name = "measured"
    if any(word in trigger_id for word in urgent_ids):
        rate_adjustment, pitch_adjustment = 2, -1
        profile_name = "controlled_urgent"
    elif any(word in trigger_id for word in opening_ids):
        rate_adjustment, pitch_adjustment = -1, 1
        profile_name = "cautious_opening"
    elif any(word in trigger_id for word in quiet_ids) or any(word in style_text for word in (
        "低声", "犹豫", "放慢", "停顿", "缓一缓", "克制",
    )):
        rate_adjustment, pitch_adjustment, volume_adjustment = -4, -1, -1
        profile_name = "quiet_reflective"
    return {
        "profile": profile_name,
        "rate_pct": max(-14, min(4, profile["base_rate_pct"] + rate_adjustment)),
        "pitch_hz": max(-8, min(4, profile["base_pitch_hz"] + pitch_adjustment)),
        "volume_pct": max(-8, min(2, profile["volume_pct"] + volume_adjustment)),
    }


def synthesize(text, profile, trigger, max_duration, output, audio_config):
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = output.with_suffix(".edge.mp3")
    controls = prosody_controls(trigger, profile)
    command = [
        "edge-tts", "--voice", profile["voice"],
        f"--rate={_signed(controls['rate_pct'], '%')}",
        f"--pitch={_signed(controls['pitch_hz'], 'Hz')}",
        f"--volume={_signed(controls['volume_pct'], '%')}",
        "--text", text, "--write-media", str(raw),
    ]
    for attempt in range(4):
        try:
            subprocess.run(command, check=True)
            break
        except subprocess.CalledProcessError:
            raw.unlink(missing_ok=True)
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    trimmed = output.with_suffix(".speech.wav")
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y", "-i", str(raw),
            "-af", (
                "areverse,silenceremove="
                "start_periods=1:start_duration=0.05:start_threshold=-45dB,areverse"
            ),
            "-ar", str(audio_config["sample_rate_hz"]), "-ac", "1", str(trimmed),
        ],
        check=True,
    )
    speech_duration = media_probe(trimmed)
    lead_seconds = audio_config["lead_silence_ms"] / 1000
    tail_seconds = audio_config["tail_silence_ms"] / 1000
    target_duration = math.ceil(
        (speech_duration + lead_seconds + tail_seconds) * 25
    ) / 25
    target_duration = max(audio_config["minimum_duration_seconds"], target_duration)
    if target_duration > audio_config["maximum_duration_seconds"]:
        raw.unlink(missing_ok=True)
        trimmed.unlink(missing_ok=True)
        raise ValueError(
            f"speech exceeds {audio_config['maximum_duration_seconds']}s asset limit: {speech_duration}s for {text}"
        )
    filter_chain = (
        f"adelay={audio_config['lead_silence_ms']},"
        "highpass=f=55,lowpass=f=10500,"
        "loudnorm=I=-19:TP=-2:LRA=11,"
        f"apad=whole_dur={target_duration},atrim=0:{target_duration}"
    )
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y", "-i", str(trimmed),
            "-af", filter_chain,
            "-ar", str(audio_config["sample_rate_hz"]), "-ac", "1", str(output),
        ],
        check=True,
    )
    raw.unlink(missing_ok=True)
    trimmed.unlink(missing_ok=True)
    return {
        **controls,
        "voice": profile["voice"],
        "speech_duration_seconds": speech_duration,
        "output_duration_seconds": media_probe(output),
        "lead_silence_ms": audio_config["lead_silence_ms"],
        "tail_silence_ms": audio_config["tail_silence_ms"],
        "sample_rate_hz": audio_config["sample_rate_hz"],
    }


def prepare(with_audio=False):
    voice_config = load(VOICE_PROFILES)
    audio_config = {key: voice_config[key] for key in (
        "sample_rate_hz", "minimum_duration_seconds", "maximum_duration_seconds",
        "lead_silence_ms", "tail_silence_ms",
    )}
    profiles = voice_config["profiles"]
    records = []
    for index, scenario_path in enumerate(discover_scenario_paths(SCENARIOS), 1):
        scenario = load(scenario_path)
        bundle = scenario_path.parent.name
        reference = ASSETS / bundle / "reference.png"
        if not reference.exists():
            raise FileNotFoundError(reference)
        profile = profiles[scenario["scenario_id"]]
        for trigger in scenario.get("video_triggers", []):
            label = trigger["trigger_id"]
            asset_id = f"{scenario['scenario_id']}--{label}"
            line = trigger["spoken_response"]
            max_duration = float(trigger.get("duration_seconds", 5))
            duration = max_duration
            audio_metadata = None
            request_path = REQUESTS / bundle / f"{label}.json"
            audio_path = ASSETS / bundle / f"{label}.wav"
            video_path = ASSETS / bundle / f"{label}.mp4"
            request_path.parent.mkdir(parents=True, exist_ok=True)
            if with_audio:
                audio_metadata = synthesize(
                    line, profile, trigger, max_duration, audio_path, audio_config
                )
                duration = audio_metadata["output_duration_seconds"]
            elif audio_path.exists():
                duration = media_probe(audio_path)
            request_path.write_text(json.dumps({
                "prompt": prompt_for(scenario, trigger, line),
                "duration_seconds": duration,
                "continuity_reference": reference.relative_to(ROOT).as_posix(),
                "safety_check": {
                    "contains_private_state": False,
                    "contains_threshold_logic": False,
                    "contains_benchmark_answer": False,
                },
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            status = "audio_ready" if with_audio else (
                "generated" if video_path.exists() else (
                    "audio_ready" if audio_path.exists() else "request_ready"
                )
            )
            records.append({
                "asset_id": asset_id,
                "scenario_id": scenario["scenario_id"],
                "scenario_title": scenario["title"],
                "trigger_label": label,
                "provider": "TMElyralab/MuseTalk 1.5",
                "provider_license": "MIT",
                "utterance": line,
                "voice": profile["voice"],
                "voice_profile": profile,
                "synthesis": audio_metadata,
                "duration_seconds": duration,
                "generation_profile": "multimodel_v4_natural_speech_musetalk_v15",
                "motion_profile": motion_profile(trigger["observable_expression"]),
                "reference_path": reference.relative_to(ROOT).as_posix(),
                "reference_sha256": sha256(reference),
                "request_path": request_path.relative_to(ROOT).as_posix(),
                "audio_path": audio_path.relative_to(ROOT).as_posix(),
                "video_path": video_path.relative_to(ROOT).as_posix(),
                "audio_sha256": sha256(audio_path) if audio_path.exists() else None,
                "audio_duration_seconds": (
                    media_probe(audio_path) if audio_path.exists() else None
                ),
                "status": status,
            })
    MEDIA.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "format": "socialflux_talking_head_assets_v2",
        "generator": "TMElyralab/MuseTalk 1.5",
        "generation_profile": "multimodel_v4_natural_speech_musetalk_v15",
        "voice_profile_config": VOICE_PROFILES.relative_to(ROOT).as_posix(),
        "asset_count": len(records),
        "assets": records,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "asset_count": len(records),
        "audio_ready": sum(item["status"] != "request_ready" for item in records),
    }, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthesize-audio", action="store_true")
    args = parser.parse_args()
    prepare(args.synthesize_audio)


if __name__ == "__main__":
    main()
