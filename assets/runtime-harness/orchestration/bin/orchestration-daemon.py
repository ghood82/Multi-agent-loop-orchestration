#!/usr/bin/env python3
"""Drive the orchestration loop from state.

Safe by default: one step, no git writes. Use --continuous or --max-steps for
longer runs. The daemon prepares/runs role prompts through run-cycle.py and
updates orchestration/state.json after each role.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_QUEUE = [
    "builder",
    "qa",
    "security",
    "eval-builder",
    "eval",
    "watchdog",
    "architect",
    "docs",
]


ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "bin"
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the orchestration daemon.")
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=30.0)
    parser.add_argument("--agent-command", default=os.environ.get("AGENT_COMMAND", ""))
    parser.add_argument("--strict-gates", action="store_true")
    parser.add_argument("--require-ci-pass", action="store_true")
    parser.add_argument("--watch-ci", action="store_true")
    parser.add_argument("--ci-pr", default="")
    parser.add_argument("--ci-required", action="store_true")
    parser.add_argument("--ci-timeout-seconds", type=float, default=0.0)
    parser.add_argument("--ci-from-file", default="")
    parser.add_argument("--require-human-approval", action="store_true")
    parser.add_argument("--remediate-on-gate-failure", action="store_true")
    parser.add_argument("--dispatch-subagents", action="store_true")
    parser.add_argument("--subagent-command", default=os.environ.get("SUBAGENT_COMMAND", ""))
    parser.add_argument("--subagent-open-blockers", action="store_true")
    parser.add_argument("--subagent-fail-on-negative", action="store_true")
    parser.add_argument("--disable-file-guard", action="store_true")
    parser.add_argument("--no-file-guard-blocker", action="store_true")
    parser.add_argument("--release-gate", action="store_true")
    parser.add_argument("--release-mode", choices=["status", "pr", "merge", "release"], default="status")
    parser.add_argument("--release-pr", default="")
    parser.add_argument("--release-pr-from-file", default="")
    parser.add_argument("--release-open-blocker", action="store_true")
    parser.add_argument("--release-strict-file-guard", action="store_true")
    parser.add_argument("--allow-draft-pr", action="store_true")
    parser.add_argument("--allow-review-pending", action="store_true")
    parser.add_argument("--resume-plan", action="store_true", help="Run resume-plan.py --apply before daemon steps.")
    parser.add_argument("--resume-prefer-remediation", action="store_true")
    parser.add_argument("--sync-state-doc", action="store_true", help="Forward --sync-state-doc to run-cycle.py after each role.")
    parser.add_argument(
        "--stop-on-blocker",
        action="store_true",
        help="Pause instead of running remediation when blockers are open.",
    )
    parser.add_argument(
        "--remediate-open-blockers",
        action="store_true",
        help="Run remediation instead of pausing when open blockers exist.",
    )
    return parser.parse_args()


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON: {exc}") from exc


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(role: str, event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": role, "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def open_blockers(state: dict[str, Any]) -> list[Any]:
    blockers = state.get("open_blockers") or []
    if not isinstance(blockers, list):
        return [blockers]
    result = []
    for blocker in blockers:
        if isinstance(blocker, dict) and blocker.get("status", "open") in {"resolved", "closed"}:
            continue
        result.append(blocker)
    return result


def queue_state(state: dict[str, Any]) -> tuple[list[str], int]:
    daemon = state.setdefault("daemon", {})
    queue = daemon.get("queue") or DEFAULT_QUEUE
    if not isinstance(queue, list) or not queue:
        queue = DEFAULT_QUEUE
    cursor = daemon.get("cursor", 0)
    if not isinstance(cursor, int):
        cursor = 0
    cursor = max(0, min(cursor, len(queue) - 1))
    return [str(role) for role in queue], cursor


def latest_watchdog_verdict(state: dict[str, Any]) -> str:
    verdict = state.get("watchdog", {}).get("last_verdict") or state.get("last_watchdog_verdict")
    return str(verdict or "").strip().upper()


def choose_role(state: dict[str, Any], args: argparse.Namespace) -> str | None:
    blockers = open_blockers(state)
    if blockers:
        if args.remediate_open_blockers and not args.stop_on_blocker:
            return "remediation"
        if state.get("daemon", {}).get("pause_on_blocker", True):
            return None
        return "remediation"

    verdict = latest_watchdog_verdict(state)
    if verdict in {"REQUEST_FIXES", "PROCESS_WARNING", "STOP"}:
        return "remediation"

    queue, cursor = queue_state(state)
    return queue[cursor]


def advance_cursor(state: dict[str, Any], role: str) -> None:
    if role == "remediation":
        return
    queue, cursor = queue_state(state)
    if queue[cursor] == role:
        state.setdefault("daemon", {})["cursor"] = (cursor + 1) % len(queue)


def run_role(role: str, args: argparse.Namespace) -> subprocess.CompletedProcess[str]:
    command = ["bash", str(BIN_DIR / "run-cycle.sh"), "--roles", role]
    if args.agent_command:
        command.extend(["--agent-command", args.agent_command])
    if args.strict_gates:
        command.append("--strict-gates")
    if args.require_ci_pass:
        command.append("--require-ci-pass")
    if args.watch_ci:
        command.append("--watch-ci")
    if args.ci_pr:
        command.extend(["--ci-pr", args.ci_pr])
    if args.ci_required:
        command.append("--ci-required")
    if args.ci_timeout_seconds > 0:
        command.extend(["--ci-timeout-seconds", str(args.ci_timeout_seconds)])
    if args.ci_from_file:
        command.extend(["--ci-from-file", args.ci_from_file])
    if args.require_human_approval:
        command.append("--require-human-approval")
    if args.remediate_on_gate_failure:
        command.append("--remediate-on-gate-failure")
    if args.dispatch_subagents:
        command.append("--dispatch-subagents")
    if args.subagent_command:
        command.extend(["--subagent-command", args.subagent_command])
    if args.subagent_open_blockers:
        command.append("--subagent-open-blockers")
    if args.subagent_fail_on_negative:
        command.append("--subagent-fail-on-negative")
    if args.disable_file_guard:
        command.append("--disable-file-guard")
    if args.no_file_guard_blocker:
        command.append("--no-file-guard-blocker")
    if args.release_gate:
        command.append("--release-gate")
    if args.release_mode:
        command.extend(["--release-mode", args.release_mode])
    if args.release_pr:
        command.extend(["--release-pr", args.release_pr])
    if args.release_pr_from_file:
        command.extend(["--release-pr-from-file", args.release_pr_from_file])
    if args.release_open_blocker:
        command.append("--release-open-blocker")
    if args.release_strict_file_guard:
        command.append("--release-strict-file-guard")
    if args.allow_draft_pr:
        command.append("--allow-draft-pr")
    if args.allow_review_pending:
        command.append("--allow-review-pending")
    if args.sync_state_doc:
        command.append("--sync-state-doc")
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def run_resume_plan(args: argparse.Namespace) -> None:
    command = ["python3", str(BIN_DIR / "resume-plan.py"), "--apply"]
    if args.resume_prefer_remediation:
        command.append("--prefer-remediation")
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        raise SystemExit(f"resume-plan.py failed:\n{result.stdout}")


def step(args: argparse.Namespace) -> bool:
    state = load_state()
    role = choose_role(state, args)
    if role is None:
        state.setdefault("daemon", {})["status"] = "paused_blocked"
        state["daemon"]["last_run_at"] = now()
        save_state(state)
        log_event("Daemon", "paused_blocked", "Open blockers require human/remediation decision")
        print("Daemon paused: open blockers present.")
        return False

    state.setdefault("daemon", {})["status"] = "running"
    state["daemon"]["last_role"] = role
    state["daemon"]["last_run_at"] = now()
    save_state(state)
    log_event("Daemon", "role_started", role)

    result = run_role(role, args)
    print(result.stdout, end="")

    state = load_state()
    if result.returncode == 0:
        advance_cursor(state, role)
        state.setdefault("daemon", {})["status"] = "idle"
        log_event("Daemon", "role_completed", role)
    else:
        state.setdefault("daemon", {})["status"] = "paused_error"
        log_event("Daemon", "role_failed", f"{role} exit={result.returncode}")
    state["daemon"]["last_role"] = role
    state["daemon"]["last_run_at"] = now()
    save_state(state)
    return result.returncode == 0


def main() -> int:
    args = parse_args()
    if args.resume_plan:
        run_resume_plan(args)
    steps = 0
    while True:
        ok = step(args)
        steps += 1
        if not ok:
            return 1
        if not args.continuous and steps >= args.max_steps:
            return 0
        if args.continuous and args.max_steps and steps >= args.max_steps:
            return 0
        time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
