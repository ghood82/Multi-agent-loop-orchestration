#!/usr/bin/env python3
"""Plan the next safe orchestration action after interruption or pause."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"

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

PASS_CI = {"success", "succeeded", "passed", "pass", "green"}
WAIT_CI = {"pending", "queued", "in_progress", "running", "waiting"}
WATCHDOG_REMEDIATE = {"REQUEST_FIXES", "PROCESS_WARNING", "STOP"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a deterministic resume plan.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update state.json with next_authorized_action and daemon cursor/status.",
    )
    parser.add_argument(
        "--prefer-remediation",
        action="store_true",
        help="Prefer remediation over pause when blockers exist.",
    )
    parser.add_argument(
        "--write-report", action="store_true", help="Write a structured resume-plan report."
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
        return [blockers] if blockers else []
    return [
        blocker
        for blocker in blockers
        if not isinstance(blocker, dict)
        or blocker.get("status", "open") not in {"resolved", "closed"}
    ]


def queue_and_cursor(state: dict[str, Any]) -> tuple[list[str], int]:
    daemon = state.setdefault("daemon", {})
    queue = daemon.get("queue") or DEFAULT_QUEUE
    if not isinstance(queue, list) or not queue:
        queue = DEFAULT_QUEUE
    queue = [str(item) for item in queue]
    cursor = daemon.get("cursor", 0)
    if not isinstance(cursor, int):
        cursor = 0
    cursor = max(0, min(cursor, len(queue) - 1))
    return queue, cursor


def latest_event() -> dict[str, Any] | None:
    if not EVENT_LOG.exists():
        return None
    last: dict[str, Any] | None = None
    for line in EVENT_LOG.read_text().splitlines():
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    return last


def ci_state(state: dict[str, Any]) -> str:
    return str(state.get("ci_status", {}).get("conclusion", "")).strip().lower()


def watchdog_state(state: dict[str, Any]) -> str:
    verdict = state.get("watchdog", {}).get("last_verdict") or state.get("last_watchdog_verdict")
    return str(verdict or "").strip().upper()


def release_state(state: dict[str, Any]) -> str:
    return str(state.get("release_gate", {}).get("last_decision", "")).strip().upper()


def blocker_mode(state: dict[str, Any]) -> str:
    policy = state.get("blocking_policy", {})
    if isinstance(policy, dict):
        return str(policy.get("mode", "stop-and-ask"))
    return "stop-and-ask"


def plan(state: dict[str, Any], prefer_remediation: bool) -> dict[str, Any]:
    blockers = open_blockers(state)
    queue, cursor = queue_and_cursor(state)
    current_role = queue[cursor]
    daemon = state.get("daemon", {})
    release = release_state(state)
    ci = ci_state(state)
    watchdog = watchdog_state(state)
    last = latest_event()

    decision = {
        "id": f"resume-plan-{compact_ts()}",
        "created_at": now(),
        "decision": "CONTINUE",
        "next_role": current_role,
        "next_action": f"Continue daemon queue with {current_role}.",
        "reason": "No blocking evidence found.",
        "evidence": {
            "open_blockers_count": len(blockers),
            "daemon_status": daemon.get("status", "unknown"),
            "daemon_cursor": cursor,
            "daemon_next_role": current_role,
            "watchdog": watchdog,
            "ci": ci,
            "release_gate": release,
            "last_event": last,
        },
    }

    if blockers:
        mode = blocker_mode(state)
        if prefer_remediation or mode in {"bounded-recovery", "docs-only-continue"}:
            decision.update(
                {
                    "decision": "REMEDIATE",
                    "next_role": "remediation",
                    "next_action": "Run Blocker Remediation for open blockers, then re-run affected verification.",
                    "reason": f"{len(blockers)} open blocker(s) remain.",
                }
            )
        else:
            decision.update(
                {
                    "decision": "PAUSE_FOR_HUMAN",
                    "next_role": "",
                    "next_action": "Stop and ask the Human Product Owner how to handle open blockers.",
                    "reason": f"{len(blockers)} open blocker(s) remain and blocking mode is {mode}.",
                }
            )
        return decision

    if release in {"WAITING"}:
        decision.update(
            {
                "decision": "WAIT",
                "next_role": "",
                "next_action": "Wait for release-gate dependencies such as PR review, branch protection, or CI, then re-run release gate.",
                "reason": "Release gate is waiting.",
            }
        )
        return decision
    if release in {"STOP"}:
        decision.update(
            {
                "decision": "REMEDIATE",
                "next_role": "remediation",
                "next_action": "Run remediation for release-gate blockers before continuing.",
                "reason": "Release gate stopped the workflow.",
            }
        )
        return decision

    if watchdog in WATCHDOG_REMEDIATE:
        decision.update(
            {
                "decision": "REMEDIATE",
                "next_role": "remediation",
                "next_action": "Run remediation for Watchdog findings before continuing.",
                "reason": f"Watchdog verdict is {watchdog}.",
            }
        )
        return decision

    if ci in WAIT_CI:
        decision.update(
            {
                "decision": "WAIT",
                "next_role": "",
                "next_action": "Wait for CI to finish, refresh CI status, then re-run release gate or Watchdog.",
                "reason": f"CI is {ci}.",
            }
        )
        return decision
    if ci and ci not in PASS_CI and ci not in {"tbd", "unknown", "missing"}:
        decision.update(
            {
                "decision": "REMEDIATE",
                "next_role": "remediation",
                "next_action": "Run remediation for failing CI, then refresh CI status.",
                "reason": f"CI is not passing: {ci}.",
            }
        )
        return decision

    if daemon.get("status") == "paused_error":
        last_role = str(daemon.get("last_role") or current_role)
        decision.update(
            {
                "decision": "RERUN_OR_REMEDIATE",
                "next_role": last_role,
                "next_action": f"Inspect the failed {last_role} report, then rerun {last_role} or run remediation.",
                "reason": "Daemon paused after a role error.",
            }
        )
        return decision

    return decision


def write_report(resume_plan: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "id": f"{compact_ts()}-resume-plan",
        "role": "resume-plan",
        "status": "completed",
        "verdict": resume_plan["decision"],
        "summary": resume_plan["next_action"],
        "created_at": now(),
        "resume_plan": resume_plan,
    }
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return path


def apply_plan(
    state: dict[str, Any], resume_plan: dict[str, Any], report_path: Path | None
) -> None:
    state["resume_plan"] = resume_plan
    state["next_authorized_action"] = resume_plan["next_action"]
    if report_path:
        rel = str(report_path.relative_to(ROOT))
        state["resume_plan"]["last_report"] = rel
        state.setdefault("structured_reports", []).append(rel)

    next_role = resume_plan.get("next_role")
    queue, _ = queue_and_cursor(state)
    if next_role and next_role in queue:
        state.setdefault("daemon", {})["cursor"] = queue.index(next_role)
    if resume_plan["decision"] in {"WAIT", "PAUSE_FOR_HUMAN"}:
        state.setdefault("daemon", {})["status"] = "paused_resume"
    else:
        state.setdefault("daemon", {})["status"] = "idle"


def main() -> int:
    args = parse_args()
    state = load_state()
    resume_plan = plan(state, args.prefer_remediation)
    report_path = write_report(resume_plan) if args.write_report or args.apply else None
    if args.apply:
        apply_plan(state, resume_plan, report_path)
        save_state(state)
    log_event("Resume Plan", resume_plan["decision"], resume_plan["next_action"])
    print(json.dumps(resume_plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
