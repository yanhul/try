"""Live Worker integration test: durable write, read-after-write, and process restart.

The HTTP client uses an explicit User-Agent to make the request identity stable.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from research.repair_checkpoint import get_checkpoint, persist_checkpoint


def configure() -> None:
    url = os.environ.get("WORKER_URL", "").strip().rstrip("/")
    token = os.environ.get("WORKER_TOKEN", "").strip()
    if not url or not token:
        raise SystemExit("BLOCKED: WORKER_URL or WORKER_TOKEN secret is missing")
    if not url.startswith("https://"):
        raise SystemExit("BLOCKED: live Worker URL must use HTTPS")
    os.environ["TRY_REPAIR_PROVIDER_URL"] = url
    os.environ["TRY_REPAIR_PROVIDER_TOKEN"] = token
    os.environ["TRY_REPAIR_WORKER_URL"] = url
    os.environ["TRY_PROVIDER_TOKEN"] = token


def resume(request_id: str, expected_phase: str, expected_version: int) -> None:
    configure()
    record = get_checkpoint(request_id=request_id)
    if record is None:
        raise SystemExit("FAIL: checkpoint disappeared after process restart")
    expected = {
        "request_id": request_id,
        "repository": "yanhul/try",
        "sha": os.environ["GITHUB_SHA"],
        "attempt": 1,
        "phase": expected_phase,
        "state": "WORKING",
        "version": expected_version,
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise SystemExit(f"FAIL: resumed checkpoint mismatch for {key}")
    print(f"PASS: fresh process resumed durable checkpoint phase={expected_phase} version={expected_version}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--request-id")
    parser.add_argument("--expected-phase", choices=["OBSERVE", "DECIDE"])
    parser.add_argument("--expected-version", type=int)
    args = parser.parse_args()
    configure()
    if args.resume:
        if not args.request_id or not args.expected_phase or args.expected_version is None:
            raise SystemExit("FAIL: incomplete resume arguments")
        resume(args.request_id, args.expected_phase, args.expected_version)
        return

    request_id = f"live-e2e-{os.environ.get('GITHUB_RUN_ID', 'local')}-{uuid.uuid4().hex}"
    sha = os.environ.get("GITHUB_SHA", "")
    if len(sha) != 40:
        raise SystemExit("BLOCKED: GITHUB_SHA is not a full commit SHA")

    first = persist_checkpoint(
        request_id=request_id, repository="yanhul/try", sha=sha,
        attempt=1, phase="OBSERVE", state="WORKING",
    )
    if first.get("version") != 1:
        raise SystemExit("FAIL: initial durable checkpoint version is not 1")
    print("PASS: live Worker acknowledged initial checkpoint and client read-after-write matched it")

    subprocess.run(
        [sys.executable, __file__, "--resume", "--request-id", request_id,
         "--expected-phase", "OBSERVE", "--expected-version", "1"],
        check=True,
        env=os.environ.copy(),
    )

    second = persist_checkpoint(
        request_id=request_id, repository="yanhul/try", sha=sha,
        attempt=1, phase="DECIDE", state="WORKING",
    )
    if second.get("version") != 2:
        raise SystemExit("FAIL: second durable transition version is not 2")
    print("PASS: live Worker accepted monotonic OBSERVE -> DECIDE transition")

    subprocess.run(
        [sys.executable, __file__, "--resume", "--request-id", request_id,
         "--expected-phase", "DECIDE", "--expected-version", "2"],
        check=True,
        env=os.environ.copy(),
    )
    print("PASS: LIVE_DURABLE_CHECKPOINT_E2E")


if __name__ == "__main__":
    main()
