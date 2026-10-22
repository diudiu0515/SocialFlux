"""Run the full Lab backend from a GitHub branch, retaining local research data.

Only fast-forward commits are deployed. Failed startup restores the last healthy
release. This process never checks out files in the research working directory.
"""
import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, capture_output=True,
                          timeout=60, **kwargs).stdout.strip()


def stop_child(child):
    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def write_status(path, **values):
    values["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def health(port, username, password_file, child, timeout=45):
    credential = username + ":" + password_file.read_text().strip()
    headers = {"Authorization": "Basic " + base64.b64encode(credential.encode()).decode()}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and child.poll() is None:
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{port}/api/lab", headers=headers)
            with opener.open(request, timeout=10) as response:
                result = json.load(response)
            if isinstance(result.get("records"), list) and result.get("paper_tables"):
                return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


def prepare_release(repository, directory, commit, environment):
    release = directory / commit
    marker = release / ".lab-release-ready"
    if not marker.exists():
        release.mkdir(parents=True, exist_ok=True)
        archive = subprocess.Popen(["git", "--git-dir", str(repository), "archive", commit],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=archive.stdout, mode="r|") as bundle:
                bundle.extractall(release, filter="data")
            if archive.wait(timeout=30):
                raise RuntimeError("Git archive failed")
        finally:
            if archive.poll() is None:
                archive.kill()
                archive.wait()
        run([sys.executable, "-c", "import web.server"], cwd=release, env=environment)
        marker.touch()
    return release


def launch(release, args, environment):
    command = [
        sys.executable, "-u", "-m", "web.server", "--host", args.host,
        "--port", str(args.port), "--username", args.username,
        "--password-file", str(args.password_file),
    ]
    if args.public_origin:
        command.extend(["--public-origin", args.public_origin])
    return subprocess.Popen(command, cwd=release, env=environment)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--username", default="socialflux")
    parser.add_argument("--public-origin")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6006)
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    for name in ("data_root", "state_dir", "password_file"):
        setattr(args, name, getattr(args, name).expanduser().resolve())
    if not args.data_root.is_dir():
        parser.error("--data-root must be an existing project directory")
    if not args.password_file.is_file() or not args.password_file.read_text().strip():
        parser.error("--password-file must contain a password")
    if args.password_file.stat().st_mode & 0o077:
        parser.error("--password-file must be readable only by its owner (chmod 600)")
    if args.interval < 30:
        parser.error("--interval must be at least 30 seconds")
    run(["git", "check-ref-format", "refs/heads/" + args.branch])
    args.state_dir.mkdir(parents=True, exist_ok=True)
    repository = args.state_dir / "repository.git"
    releases = args.state_dir / "releases"
    releases.mkdir(exist_ok=True)
    if not repository.exists():
        run(["git", "init", "--bare", str(repository)])
        run(["git", "--git-dir", str(repository), "remote", "add", "origin", args.remote])
    elif run(["git", "--git-dir", str(repository), "remote", "get-url", "origin"]) != args.remote:
        parser.error("existing deployment repository has a different origin")
    git = ["git", "--git-dir", str(repository)]
    # Seed existing history locally; downloading the full research repository
    # again can exceed startup timeouts on the server's outbound connection.
    if not run(git + ["for-each-ref", "--format=%(refname)"]):
        run(git + ["fetch", "--no-tags", str(args.data_root),
                   "+refs/heads/*:refs/remotes/local-bootstrap/*"])
    environment = {**os.environ, "SOCIALFLUX_DATA_ROOT": str(args.data_root),
                   "GIT_TERMINAL_PROMPT": "0", "PYTHONDONTWRITEBYTECODE": "1"}
    # Always import the selected release, even when the caller has PYTHONPATH set.
    environment.pop("PYTHONPATH", None)
    # Reuse this project's scoped SSH identity, never a different account/key.
    configured_ssh = subprocess.run(["git", "-C", str(args.data_root), "config", "--get",
                                     "core.sshCommand"], capture_output=True, text=True, timeout=10)
    if configured_ssh.returncode == 0 and configured_ssh.stdout.strip():
        environment["GIT_SSH_COMMAND"] = (configured_ssh.stdout.strip()
            + " -o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=2")
    active_file = args.state_dir / "active.json"
    status_file = args.state_dir / "status.json"
    current = json.loads(active_file.read_text())["commit"] if active_file.exists() else None
    child = None
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        # Restart the last healthy release without requiring GitHub availability.
        if current:
            release = prepare_release(repository, releases, current, environment)
            child = launch(release, args, environment)
            if not health(args.port, args.username, args.password_file, child):
                stop_child(child)
                raise RuntimeError("Previously healthy release failed to restart")
        while not stopping:
            try:
                run(git + ["fetch", "--no-tags", "origin", "refs/heads/" + args.branch], env=environment)
                candidate = run(git + ["rev-parse", "FETCH_HEAD^{commit}"])
                if current and candidate != current:
                    run(git + ["merge-base", "--is-ancestor", current, candidate])
                if candidate != current or child is None or child.poll() is not None:
                    release = prepare_release(repository, releases, candidate, environment)
                    stop_child(child)
                    child = launch(release, args, environment)
                    if not health(args.port, args.username, args.password_file, child):
                        stop_child(child)
                        if current:
                            child = launch(releases / current, args, environment)
                            if not health(args.port, args.username, args.password_file, child):
                                raise RuntimeError("Deployment and rollback health checks failed")
                        raise RuntimeError("Candidate failed health check; restored previous release")
                    current = candidate
                    write_status(active_file, commit=current, branch=args.branch)
                    print("Lab release healthy:", current, flush=True)
                write_status(status_file, status="healthy", commit=current, branch=args.branch,
                             data_root=str(args.data_root), port=args.port)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                # Credentials and subprocess output are deliberately omitted.
                running = child is not None and child.poll() is None
                write_status(status_file, status="update_failed" if running else "unavailable",
                             commit=current, branch=args.branch, error=type(error).__name__)
                print("Lab update failed:", type(error).__name__, flush=True)
                if not running:
                    raise
            deadline = time.monotonic() + args.interval
            while not stopping and time.monotonic() < deadline:
                if child is not None and child.poll() is not None:
                    break
                time.sleep(1)
    finally:
        stop_child(child)


if __name__ == "__main__":
    main()
