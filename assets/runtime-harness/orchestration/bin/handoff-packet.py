#!/usr/bin/env python3
"""Create a role handoff packet from orchestration state and recent evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"


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


def log_event(event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": "handoff-packet", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def get_obj(state: dict[str, Any], key: str) -> dict[str, Any]:
    value = state.get(key)
    return value if isinstance(value, dict) else {}


def current_role(state: dict[str, Any]) -> str:
    daemon = get_obj(state, "daemon")
    queue = daemon.get("queue") or []
    cursor = daemon.get("cursor", 0)
    if not isinstance(queue, list) or not queue:
        return "builder"
    if not isinstance(cursor, int):
        cursor = 0
    cursor = max(0, min(cursor, len(queue) - 1))
    return str(queue[cursor])


def open_blockers(state: dict[str, Any]) -> list[Any]:
    blockers = state.get("open_blockers") or []
    if not isinstance(blockers, list):
        return [blockers] if blockers else []
    return [
        blocker
        for blocker in blockers
        if not isinstance(blocker, dict) or blocker.get("status", "open") not in {"resolved", "closed"}
    ]


def format_value(value: Any) -> str:
    if value is None or value == "":
        return "TBD"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return json.dumps(value, sort_keys=True)


def bullet_list(value: Any) -> str:
    if not value:
        return "- TBD"
    if not isinstance(value, list):
        return f"- {format_value(value)}"
    lines: list[str] = []
    for item in value:
        if isinstance(item, dict):
            label = item.get("description") or item.get("summary") or item.get("id") or json.dumps(item, sort_keys=True)
            parts = []
            for key in ["status", "severity", "owner", "verdict", "evidence"]:
                if item.get(key):
                    parts.append(f"{key}: {item[key]}")
            suffix = f" ({'; '.join(parts)})" if parts else ""
            lines.append(f"- {label}{suffix}")
        else:
            lines.append(f"- {format_value(item)}")
    return "\n".join(lines)


def recent_events(limit: int) -> list[dict[str, Any]]:
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


def latest_report_refs(state: dict[str, Any], limit: int) -> list[str]:
    refs = state.get("structured_reports") or []
    if not isinstance(refs, list):
        return []
    return [str(ref) for ref in refs[-limit:]]


def role_constraints(role: str) -> list[str]:
    read_only = {
        "qa",
        "security",
        "eval-builder",
        "eval",
        "watchdog",
        "architect",
        "docs",
    }
    constraints = [
        "Read `orchestration/state.json` and the synced project roadmap state before acting.",
        "Do not advance to an unauthorized phase.",
        "Do not remove preserved components or make forbidden changes.",
        "Stop and report if requirements, security, schema, API compatibility, or product judgment are unclear.",
    ]
    if role == "builder":
        constraints.append("Builder is the only default loop allowed to write production code.")
        constraints.append("Add or update tests for changed behavior and run relevant validation.")
    elif role in read_only:
        constraints.append("This role is read-only for production code unless explicitly authorized.")
    if role == "docs":
        constraints.append("Documentation may update docs/state/memory artifacts, but must not change product logic.")
    if role == "remediation":
        constraints.append("Remediation should address open blockers and rerun the affected verification, not jump phases.")
    return constraints


def build_packet(state: dict[str, Any], target_role: str, event_limit: int, report_limit: int) -> str:
    write_lock = get_obj(state, "write_lock")
    phase_gate = get_obj(state, "phase_gate")
    blocking_policy = get_obj(state, "blocking_policy")
    watchdog = get_obj(state, "watchdog")
    ci_status = get_obj(state, "ci_status")
    release_gate = get_obj(state, "release_gate")
    resume_plan = get_obj(state, "resume_plan")

    events = recent_events(event_limit)
    event_lines = [
        f"- {event.get('ts', 'TBD')} {event.get('role', 'TBD')}: {event.get('event', 'TBD')} {event.get('note', '')}".strip()
        for event in events
    ]

    lines = [
        f"# Handoff Packet: {target_role}",
        "",
        f"Generated: {now()}",
        "",
        "## Project",
        "",
        f"Project: {format_value(state.get('project_name'))}",
        f"Repo: {format_value(state.get('repo'))}",
        f"Roadmap: {format_value(state.get('roadmap'))}",
        f"Current phase: {format_value(state.get('current_phase'))}",
        f"Current objective: {format_value(state.get('current_objective'))}",
        f"Active branch: {format_value(state.get('active_branch'))}",
        f"Active PR: {format_value(state.get('active_pr'))}",
        f"Shared state file: {format_value(state.get('state_file_path'))}",
        "",
        "## Next Assignment",
        "",
        f"Target role: {target_role}",
        f"Next authorized action: {format_value(state.get('next_authorized_action'))}",
        f"Resume decision: {format_value(resume_plan.get('decision'))}",
        f"Resume next action: {format_value(resume_plan.get('next_action'))}",
        f"Resume reason: {format_value(resume_plan.get('reason'))}",
        "",
        "## Scope And Locks",
        "",
        f"Active writer: {format_value(state.get('active_writer'))}",
        f"Write lock owner: {format_value(write_lock.get('owner'))}",
        f"Write lock status: {format_value(write_lock.get('status'))}",
        f"Write lock scope: {format_value(write_lock.get('scope'))}",
        f"Authorized phase: {format_value(phase_gate.get('authorized_phase'))}",
        "Allowed files:",
        bullet_list(state.get("allowed_files") or write_lock.get("allowed_files")),
        "Forbidden files:",
        bullet_list(state.get("forbidden_files") or write_lock.get("forbidden_files")),
        "Preserved components:",
        bullet_list(state.get("preserved_components")),
        "Forbidden changes:",
        bullet_list(state.get("forbidden_changes")),
        "",
        "## Gate Status",
        "",
        f"Open blockers: {len(open_blockers(state))}",
        f"Watchdog verdict: {format_value(watchdog.get('last_verdict', state.get('last_watchdog_verdict')))}",
        f"Last eval fixture: {format_value(state.get('last_eval_fixture'))}",
        f"Last eval result artifact: {format_value(state.get('last_eval_result_artifact'))}",
        f"CI conclusion: {format_value(ci_status.get('conclusion'))}",
        f"Release gate: {format_value(release_gate.get('last_decision'))}",
        f"Human approval required: {format_value(state.get('human_approval_required'))}",
        "",
        "## Open Blockers",
        "",
        bullet_list(open_blockers(state)),
        "",
        "## Last Results",
        "",
        f"Builder: {format_value(state.get('last_builder_result'))}",
        f"QA: {format_value(state.get('last_qa_result'))}",
        f"Security: {format_value(state.get('last_security_result'))}",
        f"Eval Builder: {format_value(state.get('last_eval_builder_result'))}",
        f"Eval: {format_value(state.get('last_eval_result'))}",
        f"Watchdog: {format_value(state.get('last_watchdog_verdict'))}",
        f"Remediation: {format_value(state.get('last_remediation_result'))}",
        f"Architect: {format_value(state.get('last_architect_decision'))}",
        f"Docs: {format_value(state.get('last_documentation_update'))}",
        "",
        "## Recent Structured Reports",
        "",
        bullet_list(latest_report_refs(state, report_limit)),
        "",
        "## Recent Events",
        "",
        "\n".join(event_lines) if event_lines else "- TBD",
        "",
        "## Role Rules",
        "",
        bullet_list(role_constraints(target_role)),
        "",
        "## Blocking Policy",
        "",
        f"Mode: {format_value(blocking_policy.get('mode'))}",
        f"Recovery limit: {format_value(blocking_policy.get('recovery_limit'))}",
        "Stop immediately for:",
        bullet_list(blocking_policy.get("stop_immediately_for")),
        "",
    ]
    return "\n".join(lines)


def write_packet(state: dict[str, Any], role: str, packet: str, write_report: bool) -> Path:
    handoff_dir = ROOT / "handoffs"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    safe_role = role.replace("/", "-")
    packet_path = handoff_dir / f"{compact_ts()}-{safe_role}.md"
    packet_path.write_text(packet)
    rel_packet = str(packet_path.relative_to(ROOT))
    state.setdefault("handoff_packets", []).append(rel_packet)
    state["last_handoff_packet"] = rel_packet

    if write_report:
        reports_dir = ROOT / "reports" / "json"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "id": f"{compact_ts()}-handoff-packet",
            "role": "handoff-packet",
            "status": "completed",
            "verdict": "CREATED",
            "summary": f"Handoff packet created for {role}.",
            "created_at": now(),
            "target_role": role,
            "packet": rel_packet,
        }
        report_path = reports_dir / f"{report['id']}.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        state.setdefault("structured_reports", []).append(str(report_path.relative_to(ROOT)))

    save_state(state)
    log_event("created", rel_packet)
    return packet_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", default="", help="Target role. Defaults to current daemon role.")
    parser.add_argument("--events", type=int, default=8, help="Recent events to include.")
    parser.add_argument("--reports", type=int, default=8, help="Recent structured report refs to include.")
    parser.add_argument("--write", action="store_true", help="Write packet under orchestration/handoffs/.")
    parser.add_argument("--write-report", action="store_true", help="Record packet creation as structured evidence.")
    parser.add_argument("--json", action="store_true", help="Print JSON result when writing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = load_state()
    target_role = args.role or current_role(state)
    packet = build_packet(state, target_role, max(args.events, 0), max(args.reports, 0))
    if args.write or args.write_report:
        path = write_packet(state, target_role, packet, args.write_report)
        if args.json:
            print(json.dumps({"path": str(path), "role": target_role}, indent=2, sort_keys=True))
        else:
            print(path)
    else:
        print(packet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
