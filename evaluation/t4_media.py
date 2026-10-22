"""Actual local-video transport for exploratory, explicitly labelled T4 runs."""

import base64
from copy import deepcopy
import hashlib
from pathlib import Path
import subprocess


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract_frames(path, directory, timestamps=(0.25, 1.25, 2.25, 3.25)):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    result = []
    for index, seconds in enumerate(timestamps):
        target = directory / f"{index:02d}.jpg"
        if not target.exists():
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                            "-ss", str(seconds), "-i", str(path), "-frames:v", "1",
                            "-vf", "scale=640:-2", "-q:v", "3", str(target)], check=True, timeout=45)
        if not target.is_file() or not target.stat().st_size:
            raise ValueError("video frame extraction produced no image")
        result.append({"path": str(target), "timestamp_seconds": seconds, "sha256": sha_file(target)})
    return result


def video_blocks(asset, transport):
    if sha_file(asset["path"]) != asset["sha256"]:
        raise ValueError("frozen video checksum mismatch")
    if transport == "native_video":
        data = base64.b64encode(Path(asset["path"]).read_bytes()).decode()
        return [{"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + data}}]
    if transport != "video_frames":
        raise ValueError("unsupported video transport; no text fallback")
    blocks = []
    for frame in asset["frames"]:
        if sha_file(frame["path"]) != frame["sha256"]:
            raise ValueError("frozen frame checksum mismatch")
        data = base64.b64encode(Path(frame["path"]).read_bytes()).decode()
        blocks.extend([{"type": "text", "text": f"Video timestamp {frame['timestamp_seconds']:.2f}s"},
                       {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + data}}])
    return blocks


def provider_messages(messages, provider_kind):
    if provider_kind != "anthropic":
        return messages
    result = deepcopy(messages)
    for message in result:
        content = message["content"]
        if not isinstance(content, list):
            continue
        for index, block in enumerate(content):
            if block.get("type") == "image_url":
                header, data = block["image_url"]["url"].split(",", 1)
                if not header.startswith("data:image/") or not header.endswith(";base64"):
                    raise ValueError("only local base64 images are supported")
                content[index] = {"type": "image", "source": {"type": "base64",
                                  "media_type": header[5:-7], "data": data}}
            elif block.get("type") == "video_url":
                raise ValueError("Anthropic native route does not accept video_url; select a verified transport")
    return result


def compact_media(value):
    """Preserve auditable request structure without duplicating inline media."""
    if isinstance(value, str) and value.startswith("data:") and ";base64," in value:
        return {"inline_media_sha256": hashlib.sha256(value.encode()).hexdigest(), "characters": len(value)}
    if isinstance(value, dict):
        return {k: ({"base64_sha256": hashlib.sha256(v.encode()).hexdigest(), "characters": len(v)}
                    if k == "data" and value.get("type") == "base64" and isinstance(v, str)
                    else compact_media(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [compact_media(item) for item in value]
    return value
