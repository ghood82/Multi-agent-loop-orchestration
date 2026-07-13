#!/usr/bin/env python3
"""Safely update orchestration state, reports, blockers, and approvals."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orchestration_state as ostate

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"

LAST_RESULT_FIELDS = {
    "builder": "last_builder_result",
    "qa": "last_qa_result",
    "security": "last_security_result",
    "eval-builder": "last_eval_builder_result",
    "eval": "last_eval_result",
    "watchdog": "last_watchdog_verdict",
    "remediation": "last_remediation_result",
    "architect": "last_architect_decision",
    "docs": "last_documentation_update",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def load_state() -> dict[str, Any]:
    # Acquires the shared advisory lock; held across the read-modify-write until
    # save_state (or process exit).
    return ostate.begin(STATE_FILE)


def save_state(state: dict[str, Any]) -> None:
    ostate.commit(STATE_FILE, state)


def log_event(role: str, event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": role, "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def parse_json_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def set_path(target: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = [part for part in dotted_path.split(".") if part]
    if not parts:
        raise SystemExit("Path cannot be empty.")
    current: Any = target
    for part in parts[:-1]:
        if not isinstance(current, dict):
            raise SystemExit(f"Cannot descend into non-object at {part}.")
        current = current.setdefault(part, {})
    if not isinstance(current, dict):
        raise SystemExit(f"Cannot set {dotted_path}; parent is not an object.")
    current[parts[-1]] = value


def unresolved_blockers(state: dict[str, Any]) -> list[Any]:
    blockers = state.get("open_blockers") or []
    if not isinstance(blockers, list):
        return [blockers]
    return [
        blocker
        for blocker in blockers
        if not isinstance(blocker, dict)
        or blocker.get("status", "open") not in {"resolved", "closed"}
    ]


def cmd_show(_: argparse.Namespace) -> None:
    print(json.dumps(load_state(), indent=2, sort_keys=True))


def cmd_set(args: argparse.Namespace) -> None:
    state = load_state()
    set_path(state, args.path, parse_json_value(args.value))
    save_state(state)
    log_event("State", "set", f"{args.path} updated")


def cmd_add_blocker(args: argparse.Namespace) -> None:
    state = load_state()
    blocker = {
        "id": f"blocker-{compact_ts()}",
        "status": "open",
        "severity": args.severity,
        "owner": args.owner,
        "description": args.description,
        "created_at": now(),
        "evidence": args.evidence,
    }
    state.setdefault("open_blockers", []).append(blocker)
    save_state(state)
    log_event("Blocker", "opened", blocker["description"])
    print(json.dumps(blocker, indent=2, sort_keys=True))


def cmd_resolve_blocker(args: argparse.Namespace) -> None:
    state = load_state()
    blockers = state.get("open_blockers") or []
    if not isinstance(blockers, list):
        raise SystemExit("open_blockers must be a list to resolve blockers safely.")

    remaining: list[Any] = []
    resolved: list[Any] = []
    for blocker in blockers:
        blocker_id = blocker.get("id") if isinstance(blocker, dict) else str(blocker)
        blocker_text = blocker.get("description", "") if isinstance(blocker, dict) else str(blocker)
        if args.blocker_id in {blocker_id, blocker_text}:
            if isinstance(blocker, dict):
                blocker = dict(blocker)
                blocker["status"] = "resolved"
                blocker["resolved_at"] = now()
                blocker["resolution_evidence"] = args.evidence
            else:
                blocker = {
                    "id": blocker_id,
                    "status": "resolved",
                    "description": blocker_text,
                    "resolved_at": now(),
                    "resolution_evidence": args.evidence,
                }
            resolved.append(blocker)
        else:
            remaining.append(blocker)

    if not resolved:
        raise SystemExit(f"No matching blocker found: {args.blocker_id}")
    state["open_blockers"] = remaining
    state.setdefault("resolved_blockers", []).extend(resolved)
    save_state(state)
    log_event("Blocker", "resolved", args.blocker_id)
    print(json.dumps(resolved, indent=2, sort_keys=True))


def cmd_report(args: argparse.Namespace) -> None:
    state = load_state()
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "id": f"{compact_ts()}-{args.role}",
        "role": args.role,
        "status": args.status,
        "verdict": args.verdict,
        "summary": args.summary,
        "evidence": args.evidence,
        "created_at": now(),
        "source_report": args.source_report,
    }
    report_path = reports_dir / f"{report['id']}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state.setdefault("structured_reports", []).append(str(report_path.relative_to(ROOT)))
    field = LAST_RESULT_FIELDS.get(args.role)
    if field:
        state[field] = args.verdict or args.status
    if args.role == "watchdog":
        state.setdefault("watchdog", {})["last_verdict"] = args.verdict
    save_state(state)
    log_event(args.role, "structured_report_recorded", str(report_path.relative_to(ROOT)))
    print(report_path)


def cmd_approval(args: argparse.Namespace) -> None:
    state = load_state()
    approvals_dir = ROOT / "approvals"
    approvals_dir.mkdir(parents=True, exist_ok=True)
    approval = {
        "id": f"approval-{compact_ts()}",
        "decision": args.decision,
        "approver": args.approver,
        "scope": args.scope,
        "reason": args.reason,
        "created_at": now(),
        "evidence": args.evidence,
    }
    approval_path = approvals_dir / f"{approval['id']}.json"
    approval_path.write_text(json.dumps(approval, indent=2, sort_keys=True) + "\n")
    state.setdefault("human_approvals", []).append(str(approval_path.relative_to(ROOT)))
    save_state(state)
    log_event("Human Approval", args.decision, approval["scope"])
    print(approval_path)


def cmd_ci(args: argparse.Namespace) -> None:
    state = load_state()
    state["ci_status"] = {
        "provider": args.provider,
        "source": "manual",
        "last_checked_at": now(),
        "conclusion": args.conclusion,
        "details": args.details,
        "url": args.url,
        "pr": args.pr,
        "required_only": args.required_only,
        "counts": {},
        "checks": [],
        "error": "",
    }
    save_state(state)
    log_event("CI", args.conclusion, args.details)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show")
    show.set_defaults(func=cmd_show)

    set_cmd = sub.add_parser("set")
    set_cmd.add_argument("path")
    set_cmd.add_argument("value")
    set_cmd.set_defaults(func=cmd_set)

    add_blocker = sub.add_parser("add-blocker")
    add_blocker.add_argument("description")
    add_blocker.add_argument("--severity", default="medium")
    add_blocker.add_argument("--owner", default="TBD")
    add_blocker.add_argument("--evidence", default="")
    add_blocker.set_defaults(func=cmd_add_blocker)

    resolve = sub.add_parser("resolve-blocker")
    resolve.add_argument("blocker_id")
    resolve.add_argument("--evidence", required=True)
    resolve.set_defaults(func=cmd_resolve_blocker)

    report = sub.add_parser("record-report")
    report.add_argument("--role", required=True, choices=sorted(LAST_RESULT_FIELDS))
    report.add_argument("--status", required=True)
    report.add_argument("--verdict", default="")
    report.add_argument("--summary", default="")
    report.add_argument("--evidence", default="")
    report.add_argument("--source-report", default="")
    report.set_defaults(func=cmd_report)

    approval = sub.add_parser("approval")
    approval.add_argument("--decision", required=True, choices=["approved", "rejected"])
    approval.add_argument("--approver", required=True)
    approval.add_argument("--scope", required=True)
    approval.add_argument("--reason", default="")
    approval.add_argument("--evidence", default="")
    approval.set_defaults(func=cmd_approval)

    ci = sub.add_parser("ci")
    ci.add_argument("--provider", default="github")
    ci.add_argument("--conclusion", required=True)
    ci.add_argument("--details", default="")
    ci.add_argument("--url", default="")
    ci.add_argument("--pr", default="")
    ci.add_argument("--required-only", action="store_true")
    ci.set_defaults(func=cmd_ci)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
