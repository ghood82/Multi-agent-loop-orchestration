#!/usr/bin/env python3
"""Capture pull-request CI/check status into orchestration state.

Defaults to GitHub CLI (`gh pr checks`) when available. Use --from-file for
offline tests or custom adapters that produce the same JSON shape.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"

PASS_BUCKETS = {"pass", "skipping"}
FAIL_BUCKETS = {"fail"}
PENDING_BUCKETS = {"pending"}
CANCEL_BUCKETS = {"cancel"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch PR CI status and update orchestration state."
    )
    parser.add_argument("--provider", default="github")
    parser.add_argument(
        "--pr", default="", help="PR number, URL, or branch. Defaults to current branch PR."
    )
    parser.add_argument("--required", action="store_true", help="Only inspect required PR checks.")
    parser.add_argument("--watch", action="store_true", help="Poll until checks finish or timeout.")
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument(
        "--repo", default="", help="GitHub repo in HOST/OWNER/REPO or OWNER/REPO form."
    )
    parser.add_argument(
        "--from-file", default="", help="Read gh pr checks JSON from a file instead of calling gh."
    )
    return parser.parse_args()


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON: {exc}") from exc


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(event: str, note: str) -> None:
    entry = {"ts": now(), "role": "CI Monitor", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def git_root(start: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip()).resolve()
    return ROOT


def gh_checks(args: argparse.Namespace) -> tuple[int, str]:
    if not shutil.which("gh"):
        return 127, "GitHub CLI `gh` is not installed or not on PATH."

    command = [
        "gh",
        "pr",
        "checks",
        "--json",
        "bucket,completedAt,description,event,link,name,startedAt,state,workflow",
    ]
    if args.required:
        command.append("--required")
    if args.repo:
        command.extend(["--repo", args.repo])
    if args.pr:
        command.append(args.pr)

    result = subprocess.run(
        command,
        cwd=git_root(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode, result.stdout


def load_checks(args: argparse.Namespace) -> tuple[int, str]:
    if args.from_file:
        return 0, Path(args.from_file).read_text()
    return gh_checks(args)


def normalize_checks(raw: str) -> list[dict[str, Any]]:
    try:
        checks = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(f"CI output was not valid JSON: {exc}") from exc
    if not isinstance(checks, list):
        raise ValueError("CI output must be a JSON array.")
    return [check for check in checks if isinstance(check, dict)]


def summarize(checks: list[dict[str, Any]]) -> tuple[str, dict[str, int], str, str]:
    counts = {"pass": 0, "fail": 0, "pending": 0, "skipping": 0, "cancel": 0, "unknown": 0}
    failed: list[str] = []
    pending: list[str] = []
    first_url = ""

    for check in checks:
        bucket = str(check.get("bucket") or "").strip().lower() or "unknown"
        if bucket not in counts:
            bucket = "unknown"
        counts[bucket] += 1
        name = str(check.get("name") or check.get("workflow") or "unnamed check")
        if not first_url and check.get("link"):
            first_url = str(check["link"])
        if bucket in FAIL_BUCKETS | CANCEL_BUCKETS:
            failed.append(name)
        elif bucket in PENDING_BUCKETS or bucket == "unknown":
            pending.append(name)

    if not checks:
        return "unknown", counts, "No PR checks returned.", first_url
    if failed:
        return "failure", counts, "Failing/cancelled checks: " + ", ".join(failed[:8]), first_url
    if pending:
        return "pending", counts, "Pending/unknown checks: " + ", ".join(pending[:8]), first_url
    if all(str(check.get("bucket") or "").strip().lower() in PASS_BUCKETS for check in checks):
        return "success", counts, "All checks passed or were skipped.", first_url
    return "unknown", counts, "Unable to classify one or more checks.", first_url


def write_ci_status(
    args: argparse.Namespace,
    conclusion: str,
    details: str,
    checks: list[dict[str, Any]],
    counts: dict[str, int],
    url: str = "",
    error: str = "",
) -> None:
    state = load_state()
    state["ci_status"] = {
        "provider": args.provider,
        "source": "gh pr checks" if not args.from_file else args.from_file,
        "last_checked_at": now(),
        "conclusion": conclusion,
        "details": details,
        "url": url,
        "pr": args.pr or "current-branch",
        "required_only": bool(args.required),
        "counts": counts,
        "checks": checks,
        "error": error,
    }
    save_state(state)
    log_event(conclusion, details or error)


def capture_once(args: argparse.Namespace) -> str:
    code, raw = load_checks(args)
    if code not in {0, 8}:
        write_ci_status(args, "error", "Unable to read PR checks.", [], {}, error=raw.strip())
        return "error"

    try:
        checks = normalize_checks(raw)
    except ValueError as exc:
        write_ci_status(args, "error", str(exc), [], {}, error=raw[:2000])
        return "error"

    conclusion, counts, details, url = summarize(checks)
    write_ci_status(args, conclusion, details, checks, counts, url=url)
    return conclusion


def exit_code_for(conclusion: str) -> int:
    if conclusion == "success":
        return 0
    if conclusion == "pending":
        return 8
    return 1


def main() -> int:
    args = parse_args()
    deadline = time.monotonic() + max(args.timeout_seconds, 0)

    while True:
        conclusion = capture_once(args)
        if not args.watch or conclusion not in {"pending", "unknown"}:
            print(f"CI conclusion: {conclusion}")
            return exit_code_for(conclusion)
        if time.monotonic() >= deadline:
            print(f"CI conclusion: {conclusion} (timeout)")
            return exit_code_for(conclusion)
        time.sleep(max(args.interval, 1))


if __name__ == "__main__":
    raise SystemExit(main())
