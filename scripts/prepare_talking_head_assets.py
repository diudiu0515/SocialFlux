#!/usr/bin/env python3
"""Prepare safe talking-head requests and speech assets."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.scenario_docs import discover_scenario_paths

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "configs" / "scenarios"
MEDIA = ROOT / "media" / "talking_head"
ASSETS = MEDIA / "assets"
REQUESTS = MEDIA / "requests"
MANIFEST = MEDIA / "manifest.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utterance(expression):
    text = " ".join(str(value) for value in expression.values())
    if any(word in text for word in ("缓和", "放松", "重新看向", "倾听", "允许")):
        return "我听见你的顾虑了，请把方案具体说清楚。"
    if any(word in text for word in ("不安", "低头", "犹豫", "疲惫", "哽咽")):
        return "我需要一点时间，也请你把关键事实说清楚。"
    if any(word in text for word in ("收紧", "绷紧", "加重", "打断", "短促", "强硬")):
        return "这件事不能再拖了，请直接说明你的方案。"
    return "我明白你的意思，我们把下一步说清楚。"


def prompt_for(scenario, trigger, line):
    expression = trigger["observable_expression"]
    cues = "；".join(expression.get("behavioral_cues", []))
    role = scenario["environment_agent"]["persona"].get("role", "对话者")
    return (
        "写实电影感中近景，固定机位，单人出镜，保持参考肖像身份、服装与背景一致。"
        f"角色是{role}，自然地说普通话：‘{line}’"
        f"面部：{expression.get('facial_expression', '自然克制')}；"
        f"视线：{expression.get('gaze', '自然注视')}；"
        f"说话方式：{expression.get('speech_style', '正常语速')}；"
        f"韵律：{expression.get('prosody', '克制')}；"
        f"动作：{cues or '轻微自然头部动作'}。"
        "口型同步，动作细微连续，不夸张，不切镜，无字幕、标签、水印或其他人物。"
    )


def synthesize(text, voice, duration, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = output.with_suffix(".edge.mp3")
    subprocess.run(
        ["edge-tts", "--voice", voice, "--text", text, "--write-media", str(raw)],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y", "-i", str(raw),
            "-af", f"apad=pad_dur={duration}", "-t", str(duration),
            "-ar", "16000", "-ac", "1", str(output),
        ],
        check=True,
    )
    raw.unlink(missing_ok=True)


def prepare(with_audio=False):
    records = []
    for index, scenario_path in enumerate(discover_scenario_paths(SCENARIOS), 1):
        scenario = load(scenario_path)
        bundle = scenario_path.parent.name
        reference = ASSETS / bundle / "reference.png"
        if not reference.exists():
            raise FileNotFoundError(reference)
        voice = "zh-CN-XiaoxiaoNeural" if index % 2 else "zh-CN-YunxiNeural"
        for trigger in scenario.get("video_triggers", []):
            label = trigger["trigger_id"]
            asset_id = f"{scenario['scenario_id']}--{label}"
            line = utterance(trigger["observable_expression"])
            duration = float(trigger.get("duration_seconds", 5))
            request_path = REQUESTS / bundle / f"{label}.json"
            audio_path = ASSETS / bundle / f"{label}.wav"
            video_path = ASSETS / bundle / f"{label}.mp4"
            request_path.parent.mkdir(parents=True, exist_ok=True)
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
            if with_audio and not audio_path.exists():
                synthesize(line, voice, duration, audio_path)
            records.append({
                "asset_id": asset_id,
                "scenario_id": scenario["scenario_id"],
                "scenario_title": scenario["title"],
                "trigger_label": label,
                "provider": "BadToBest/EchoMimicV2",
                "provider_license": "Apache-2.0",
                "utterance": line,
                "voice": voice,
                "duration_seconds": duration,
                "reference_path": reference.relative_to(ROOT).as_posix(),
                "reference_sha256": sha256(reference),
                "request_path": request_path.relative_to(ROOT).as_posix(),
                "audio_path": audio_path.relative_to(ROOT).as_posix(),
                "video_path": video_path.relative_to(ROOT).as_posix(),
                "status": "generated" if video_path.exists() else (
                    "audio_ready" if audio_path.exists() else "request_ready"
                ),
            })
    MEDIA.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "format": "socialflux_talking_head_assets_v1",
        "generator": "BadToBest/EchoMimicV2",
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
