#!/usr/bin/env python3
"""Show the current orchestration operating status and next recommended action."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"

PASS_CI = {"success", "succeeded", "passed", "pass", "green"}
WAIT_CI = {"pending", "queued", "in_progress", "running", "waiting"}
GOOD_WATCHDOG = {"PASS"}
WAIT_RELEASE = {"WAITING"}
STOP_RELEASE = {"STOP"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def load_state() -> dict[str, Any]:
    try:
        state = json.loads(STATE_FILE.read_text())
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing state file: {STATE_FILE}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise SystemExit("state.json must contain an object.")
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


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


def approval_count(state: dict[str, Any]) -> int:
    approvals = state.get("human_approvals") or []
    return len(approvals) if isinstance(approvals, list) else 0


def get_obj(state: dict[str, Any], key: str) -> dict[str, Any]:
    value = state.get(key)
    return value if isinstance(value, dict) else {}


def read_recent_events(limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or not EVENT_LOG.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in EVENT_LOG.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events[-limit:]


def current_role(state: dict[str, Any]) -> str:
    daemon = get_obj(state, "daemon")
    queue = daemon.get("queue") or []
    cursor = daemon.get("cursor", 0)
    if not isinstance(queue, list) or not queue:
        return "TBD"
    if not isinstance(cursor, int):
        cursor = 0
    cursor = max(0, min(cursor, len(queue) - 1))
    return str(queue[cursor])


def verdict(value: Any) -> str:
    text = str(value or "TBD").strip()
    return text or "TBD"


def choose_recommendation(snapshot: dict[str, Any]) -> tuple[str, str]:
    blockers_count = snapshot["blockers"]["count"]
    health = snapshot["health_check"]["last_decision"].upper()
    release = snapshot["release_gate"]["last_decision"].upper()
    phase = snapshot["phase_gate"]["last_decision"].upper()
    watchdog = snapshot["watchdog"]["last_verdict"].upper()
    ci = snapshot["ci_status"]["conclusion"].lower()
    daemon_status = snapshot["daemon"]["status"]
    next_role = snapshot["daemon"]["current_role"]

    if health == "FAIL":
        return (
            "STOP",
            "Fix harness health-check failures, then run `python3 orchestration/bin/health-check.py --write-report`.",
        )
    if blockers_count:
        return (
            "REMEDIATE",
            "Run `python3 orchestration/bin/resume-plan.py --apply --prefer-remediation --write-report`, then run the remediation loop.",
        )
    if release in STOP_RELEASE:
        return (
            "REMEDIATE",
            "Run Blocker Remediation for release-gate findings, then re-run `python3 orchestration/bin/release-gate.py`.",
        )
    if phase == "STOP":
        return (
            "REMEDIATE",
            "Resolve phase-gate blockers, then re-run `python3 orchestration/bin/phase-gate.py --write-report`.",
        )
    if release in WAIT_RELEASE:
        return (
            "WAIT",
            "Wait for release dependencies such as PR review, branch protection, or CI, then re-run release gate.",
        )
    if watchdog and watchdog not in GOOD_WATCHDOG and watchdog != "TBD":
        return (
            "REMEDIATE",
            "Run Blocker Remediation for Watchdog findings before continuing the daemon.",
        )
    if ci in WAIT_CI:
        return (
            "WAIT",
            "Wait for CI to finish, then run `bash orchestration/bin/watch-ci.sh --required`.",
        )
    if ci and ci not in PASS_CI and ci not in {"tbd", "unknown", "missing"}:
        return (
            "REMEDIATE",
            "Run remediation for failing CI, then refresh CI status.",
        )
    if daemon_status in {"paused", "paused_error"}:
        return (
            "RESUME_PLAN",
            "Run `python3 orchestration/bin/resume-plan.py --apply --write-report` before restarting the daemon.",
        )
    return (
        "CONTINUE",
        f"Run the next authorized role with `bash orchestration/bin/orchestration-daemon.sh --resume-plan --max-steps 1`."
        f" Next role: {next_role}.",
    )


def build_snapshot(state: dict[str, Any], event_limit: int) -> dict[str, Any]:
    daemon = get_obj(state, "daemon")
    watchdog = get_obj(state, "watchdog")
    ci_status = get_obj(state, "ci_status")
    release_gate = get_obj(state, "release_gate")
    phase_gate = get_obj(state, "phase_gate")
    operating_policy = get_obj(state, "operating_policy")
    policy_audit = get_obj(state, "policy_audit")
    health_check = get_obj(state, "health_check")
    resume_plan = get_obj(state, "resume_plan")
    blockers = open_blockers(state)

    snapshot: dict[str, Any] = {
        "id": f"operator-status-{compact_ts()}",
        "role": "operator-status",
        "created_at": now(),
        "project": {
            "name": state.get("project_name", "TBD"),
            "repo": state.get("repo", "TBD"),
            "roadmap": state.get("roadmap", "TBD"),
            "current_phase": state.get("current_phase", "TBD"),
            "current_objective": state.get("current_objective", "TBD"),
            "active_branch": state.get("active_branch", "TBD"),
            "active_pr": state.get("active_pr", "TBD"),
        },
        "daemon": {
            "enabled": daemon.get("enabled", False),
            "status": daemon.get("status", "TBD"),
            "cursor": daemon.get("cursor", "TBD"),
            "current_role": current_role(state),
            "queue": daemon.get("queue", []),
            "last_role": daemon.get("last_role", "TBD"),
            "last_run_at": daemon.get("last_run_at", "TBD"),
        },
        "blockers": {
            "count": len(blockers),
            "items": blockers,
        },
        "health_check": {
            "last_decision": verdict(health_check.get("last_decision")),
            "last_checked_at": health_check.get("last_checked_at", "TBD"),
            "failures": health_check.get("failures", []),
            "warnings": health_check.get("warnings", []),
        },
        "watchdog": {
            "last_verdict": verdict(
                watchdog.get("last_verdict", state.get("last_watchdog_verdict"))
            ),
            "product_quality_status": watchdog.get("product_quality_status", "TBD"),
            "eval_quality_status": watchdog.get("eval_quality_status", "TBD"),
            "process_integrity_status": watchdog.get("process_integrity_status", "TBD"),
        },
        "evals": {
            "fixtures_count": len(state.get("eval_fixtures") or [])
            if isinstance(state.get("eval_fixtures"), list)
            else 0,
            "results_count": len(state.get("eval_results") or [])
            if isinstance(state.get("eval_results"), list)
            else 0,
            "last_fixture": state.get("last_eval_fixture", "TBD"),
            "last_result_artifact": state.get("last_eval_result_artifact", "TBD"),
            "last_result": state.get("last_eval_result", "TBD"),
        },
        "ci_status": {
            "conclusion": verdict(ci_status.get("conclusion")),
            "provider": ci_status.get("provider", "TBD"),
            "last_checked_at": ci_status.get("last_checked_at", "TBD"),
            "url": ci_status.get("url", "TBD"),
        },
        "release_gate": {
            "last_decision": verdict(release_gate.get("last_decision")),
            "last_checked_at": release_gate.get("last_checked_at", "TBD"),
            "mode": release_gate.get("mode", "TBD"),
            "blocking": release_gate.get("blocking", []),
            "warnings": release_gate.get("warnings", []),
        },
        "phase_gate": {
            "authorized_phase": phase_gate.get(
                "authorized_phase", state.get("current_phase", "TBD")
            ),
            "last_decision": verdict(phase_gate.get("last_decision")),
            "last_checked_at": phase_gate.get("last_checked_at", "TBD"),
            "blocking": phase_gate.get("blocking", []),
            "warnings": phase_gate.get("warnings", []),
        },
        "operating_policy": {
            "path": operating_policy.get("path", "operating-policy.json"),
            "profile": operating_policy.get("profile", "TBD"),
            "last_loaded_at": operating_policy.get("last_loaded_at", "TBD"),
        },
        "policy_audit": {
            "last_decision": verdict(policy_audit.get("last_decision")),
            "last_checked_at": policy_audit.get("last_checked_at", "TBD"),
            "policy_profile": policy_audit.get("policy_profile", "TBD"),
            "missing_evidence": policy_audit.get("missing_evidence", []),
        },
        "resume_plan": {
            "decision": resume_plan.get("decision", "TBD"),
            "next_role": resume_plan.get("next_role", "TBD"),
            "next_action": resume_plan.get("next_action", "TBD"),
            "reason": resume_plan.get("reason", "TBD"),
        },
        "approvals": {
            "count": approval_count(state),
            "human_approval_required": state.get("human_approval_required", True),
        },
        "last_results": {
            "builder": state.get("last_builder_result", "TBD"),
            "qa": state.get("last_qa_result", "TBD"),
            "security": state.get("last_security_result", "TBD"),
            "eval_builder": state.get("last_eval_builder_result", "TBD"),
            "eval": state.get("last_eval_result", "TBD"),
            "watchdog": state.get("last_watchdog_verdict", "TBD"),
            "remediation": state.get("last_remediation_result", "TBD"),
            "architect": state.get("last_architect_decision", "TBD"),
            "docs": state.get("last_documentation_update", "TBD"),
        },
        "next_authorized_action": state.get("next_authorized_action", "TBD"),
        "recent_events": read_recent_events(event_limit),
    }
    decision, recommendation = choose_recommendation(snapshot)
    snapshot["operating_decision"] = decision
    snapshot["recommended_next_action"] = recommendation
    return snapshot


def write_report(state: dict[str, Any], snapshot: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "id": snapshot["id"],
        "role": "operator-status",
        "status": "completed",
        "verdict": snapshot["operating_decision"],
        "summary": snapshot["recommended_next_action"],
        "created_at": snapshot["created_at"],
        "snapshot": snapshot,
    }
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state.setdefault("structured_reports", []).append(str(path.relative_to(ROOT)))
    state["operator_status"] = {
        "last_decision": snapshot["operating_decision"],
        "last_checked_at": snapshot["created_at"],
        "last_report": str(path.relative_to(ROOT)),
        "recommended_next_action": snapshot["recommended_next_action"],
    }
    save_state(state)
    return path


def print_markdown(snapshot: dict[str, Any], report_path: Path | None) -> None:
    project = snapshot["project"]
    daemon = snapshot["daemon"]
    print("# Orchestration Status")
    print(f"Project: {project['name']}")
    print(f"Repo: {project['repo']}")
    print(f"Roadmap: {project['roadmap']}")
    print(f"Phase: {project['current_phase']}")
    print(f"Objective: {project['current_objective']}")
    print()
    print(f"Operating decision: {snapshot['operating_decision']}")
    print(f"Recommended next action: {snapshot['recommended_next_action']}")
    print(f"Next authorized action: {snapshot['next_authorized_action']}")
    if report_path:
        print(f"Report: {report_path}")
    print()
    print("## Gates")
    print(f"- Open blockers: {snapshot['blockers']['count']}")
    print(f"- Health check: {snapshot['health_check']['last_decision']}")
    print(f"- Watchdog: {snapshot['watchdog']['last_verdict']}")
    print(
        f"- Eval results: {snapshot['evals']['results_count']} recorded; latest {snapshot['evals']['last_result']}"
    )
    print(f"- CI: {snapshot['ci_status']['conclusion']}")
    print(f"- Release gate: {snapshot['release_gate']['last_decision']}")
    print(f"- Human approvals: {snapshot['approvals']['count']}")
    print()
    print("## Daemon")
    print(f"- Status: {daemon['status']}")
    print(f"- Current role: {daemon['current_role']}")
    print(f"- Cursor: {daemon['cursor']}")
    print(f"- Last role: {daemon['last_role']}")
    print()
    print("## Last Results")
    for role, result in snapshot["last_results"].items():
        print(f"- {role}: {result}")
    if snapshot["recent_events"]:
        print()
        print("## Recent Events")
        for event in snapshot["recent_events"]:
            print(
                f"- {event.get('ts', 'TBD')} {event.get('role', 'TBD')}: {event.get('event', 'TBD')} {event.get('note', '')}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown.")
    parser.add_argument("--events", type=int, default=5, help="Number of recent events to include.")
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write an operator-status report and update state.json.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero unless operating decision is CONTINUE.",
    )
    return parser.parse_args()


def exit_code(snapshot: dict[str, Any], strict: bool) -> int:
    decision = snapshot["operating_decision"]
    if decision == "STOP":
        return 2
    if strict and decision != "CONTINUE":
        return 1
    return 0


def main() -> int:
    args = parse_args()
    state = load_state()
    snapshot = build_snapshot(state, max(args.events, 0))
    report_path = write_report(state, snapshot) if args.write_report else None
    if args.json:
        output = dict(snapshot)
        if report_path:
            output["report_path"] = str(report_path)
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print_markdown(snapshot, report_path)
    return exit_code(snapshot, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
