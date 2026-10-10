#!/usr/bin/env python3
"""Submit, resume, download, and record an AutoDL Seedance video task."""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlparse

import requests


CREATE_URL = "https://www.autodl.art/api/v1/ark/v3/contents/generations/tasks"
ALLOWED_MODELS = {
    "doubao-seedance-2-0-260128",
    "doubao-seedance-2-0-fast-260128",
    "doubao-seedance-2-0-mini-260615",
}
TERMINAL_STATUSES = {"succeeded", "failed", "expired", "cancelled"}
CJK = re.compile(r"[\u3400-\u9fff]")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prompt_text(payload):
    return "\n".join(
        str(item.get("text", ""))
        for item in payload.get("content", [])
        if item.get("type") == "text"
    ).strip()


def provider_reference_url(path):
    """Resolve a local anchor to its matching provider-hosted HTTPS URL."""
    path = Path(path)
    expected_sha = sha256(path)
    state_root = path.parent.parent / "provider_states"
    for state_path in sorted(state_root.glob(f"{path.stem}*.json")):
        state = load(state_path)
        if state.get("status") != "downloaded":
            continue
        if state.get("video_sha256") != expected_sha:
            continue
        url = str(
            ((state.get("latest_query_response") or {}).get("content") or {}).get(
                "video_url", ""
            )
        )
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.netloc:
            return url
    raise ValueError(
        "downloaded provider state with matching SHA and HTTPS reference URL "
        f"not found for {path}; regenerate or host the anchor before dependents"
    )


def materialize_local_references(payload):
    """Materialize an explicitly selected local-reference transport."""
    result = deepcopy(payload)
    reference = result.pop("local_reference_video", None)
    transport = result.pop("local_reference_transport", "provider_url")
    supplied_url = result.pop("local_reference_url", None)
    if reference is None:
        return result
    path = Path(reference)
    if not path.is_file():
        raise ValueError(f"local reference video is missing: {path}")
    if transport == "data_uri":
        if path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("inline reference video exceeds the 20 MiB request budget")
        reference_url = "data:video/mp4;base64," + base64.b64encode(path.read_bytes()).decode()
    elif transport == "provided_url":
        parsed = urlparse(str(supplied_url or ""))
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("provided reference must be a valid HTTPS URL")
        reference_url = supplied_url
    elif transport == "provider_url":
        reference_url = provider_reference_url(path)
    else:
        raise ValueError("unsupported local reference transport")
    result.setdefault("content", []).append({
        "type": "video_url",
        "video_url": {"url": reference_url},
        "role": "reference_video",
    })
    return result


def validate_payload(payload):
    model = payload.get("model")
    if model not in ALLOWED_MODELS:
        raise ValueError(f"unsupported Seedance model: {model}")
    prompt = prompt_text(payload)
    if not prompt:
        raise ValueError("Seedance request requires a text prompt")
    if CJK.search(prompt):
        raise ValueError("Seedance prompt must be entirely English")
    duration = int(payload.get("duration", 0))
    if not 4 <= duration <= 15:
        raise ValueError("Seedance 2.0 duration must be in 4..15 seconds")
    if payload.get("resolution") not in {"480p", "720p", "1080p"}:
        raise ValueError("unsupported Seedance resolution")
    if not isinstance(payload.get("generate_audio"), bool):
        raise ValueError("Seedance generate_audio must be boolean")
    if payload.get("ratio", "16:9") not in {
        "16:9", "9:16", "1:1", "4:3", "3:4"
    }:
        raise ValueError("unsupported Seedance ratio")
    if payload.get("watermark") is not False:
        raise ValueError("SocialFlux Seedance requests must disable watermarks")
    if "camera_fixed" in payload:
        raise ValueError("camera_fixed is unsupported for Seedance 2.0 text-to-video")
    return payload


def video_url(result):
    url = str((result.get("content") or {}).get("video_url", ""))
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("successful Seedance result has no safe HTTPS video URL")
    return url


class SeedanceClient:
    def __init__(self, token):
        self.session = requests.Session()
        # AutoDL direct works reliably in this environment; the local proxy does not.
        self.session.trust_env = False
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def submit(self, payload):
        response = self.session.post(
            CREATE_URL,
            headers=self.headers,
            json=validate_payload(payload),
            timeout=60,
        )
        if not response.ok:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text[:2000]
            raise RuntimeError(json.dumps({
                "status_code": response.status_code,
                "provider_error": detail,
            }, ensure_ascii=False))
        result = response.json()
        if not result.get("id"):
            raise ValueError("Seedance submission returned no task id")
        return result

    def query(self, task_id):
        response = self.session.get(
            f"{CREATE_URL}/{task_id}",
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def download(self, url, output):
        response = self.session.get(url, timeout=120)
        response.raise_for_status()
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_bytes(response.content)
        temporary.replace(output)
        return output


def run(args):
    state = load(args.state)
    payload = validate_payload(materialize_local_references(state["request"]))
    token = args.key_file.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("empty AutoDL video token")
    client = SeedanceClient(token)
    task_id = state.get("task_id")
    if not task_id:
        if not args.submit_new:
            raise ValueError("--submit-new is required for a new paid video request")
        submitted = client.submit(payload)
        task_id = submitted["id"]
        state.update({
            "task_id": task_id,
            "submit_response": submitted,
            "submitted_at_utc": utc_now(),
            "status": "submitted",
        })
        atomic(args.state, state)

    deadline = time.monotonic() + args.max_wait_seconds
    while True:
        result = client.query(task_id)
        status = str(result.get("status", "unknown")).lower()
        state.update({
            "latest_query_response": result,
            "last_polled_at_utc": utc_now(),
            "status": status,
        })
        atomic(args.state, state)
        print(json.dumps({"task_id": task_id, "status": status}), flush=True)
        if status in TERMINAL_STATUSES:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Seedance task still {status} at polling deadline")
        time.sleep(args.poll_seconds)

    if status != "succeeded":
        raise RuntimeError(json.dumps(result.get("error") or result, ensure_ascii=False))
    output = client.download(video_url(result), args.output)
    state.update({
        "status": "downloaded",
        "downloaded_at_utc": utc_now(),
        "video_file": str(output),
        "video_bytes": output.stat().st_size,
        "video_sha256": sha256(output),
    })
    atomic(args.state, state)
    print(json.dumps({
        "task_id": task_id,
        "status": state["status"],
        "video_file": str(output),
        "video_bytes": state["video_bytes"],
        "video_sha256": state["video_sha256"],
    }, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--key-file",
        type=Path,
        default=Path("/root/.config/socialflux/autodl_video_api_key"),
    )
    parser.add_argument("--submit-new", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--max-wait-seconds", type=int, default=1800)
    args = parser.parse_args(argv)
    run(args)


if __name__ == "__main__":
    main()
