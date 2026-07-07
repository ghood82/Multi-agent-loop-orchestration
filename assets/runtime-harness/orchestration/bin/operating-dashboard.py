#!/usr/bin/env python3
"""Generate a human-readable operating dashboard from orchestration state."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"
DEFAULT_DASHBOARD = ROOT / "operating-dashboard.md"


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
    entry = {"ts": now(), "role": "operating-dashboard", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_obj(state: dict[str, Any], key: str) -> dict[str, Any]:
    value = state.get(key)
    return value if isinstance(value, dict) else {}


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
            label = (
                item.get("description")
                or item.get("summary")
                or item.get("name")
                or item.get("id")
                or json.dumps(item, sort_keys=True)
            )
            parts = []
            for key in ["status", "severity", "owner", "evidence", "missing"]:
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


def render_dashboard(state: dict[str, Any], event_limit: int, generated_at: str) -> str:
    daemon = get_obj(state, "daemon")
    write_lock = get_obj(state, "write_lock")
    phase_gate = get_obj(state, "phase_gate")
    release_gate = get_obj(state, "release_gate")
    policy = get_obj(state, "operating_policy")
    policy_audit = get_obj(state, "policy_audit")
    health = get_obj(state, "health_check")
    acceptance = get_obj(state, "acceptance_audit")
    operator = get_obj(state, "operator_status")
    watchdog = get_obj(state, "watchdog")
    ci = get_obj(state, "ci_status")
    resume = get_obj(state, "resume_plan")
    blockers = open_blockers(state)
    events = recent_events(event_limit)

    lines = [
        "# Operating Dashboard",
        "",
        f"Generated: {generated_at}",
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
        "",
        "## Operating Decision",
        "",
        f"Operator status: {format_value(operator.get('last_decision'))}",
        f"Recommended next action: {format_value(operator.get('recommended_next_action', state.get('next_authorized_action')))}",
        f"Next authorized action: {format_value(state.get('next_authorized_action'))}",
        f"Resume decision: {format_value(resume.get('decision'))}",
        f"Resume next action: {format_value(resume.get('next_action'))}",
        "",
        "## Gates",
        "",
        f"Open blockers: {len(blockers)}",
        f"Health check: {format_value(health.get('last_decision'))}",
        f"Acceptance audit: {format_value(acceptance.get('last_decision'))}",
        f"Policy profile: {format_value(policy.get('profile'))}",
        f"Policy audit: {format_value(policy_audit.get('last_decision'))}",
        f"Watchdog: {format_value(watchdog.get('last_verdict', state.get('last_watchdog_verdict')))}",
        f"Eval latest result: {format_value(state.get('last_eval_result'))}",
        f"CI conclusion: {format_value(ci.get('conclusion'))}",
        f"Release gate: {format_value(release_gate.get('last_decision'))}",
        f"Phase gate: {format_value(phase_gate.get('last_decision'))}",
        f"Human approval required: {format_value(state.get('human_approval_required'))}",
        f"Human approvals: {len(state.get('human_approvals') or []) if isinstance(state.get('human_approvals'), list) else 0}",
        "",
        "## Active Scope",
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
        "",
        "## Eval Status",
        "",
        f"Eval quality status: {format_value(state.get('eval_quality_status'))}",
        f"Last eval fixture: {format_value(state.get('last_eval_fixture'))}",
        f"Last eval result artifact: {format_value(state.get('last_eval_result_artifact'))}",
        "Eval fixtures:",
        bullet_list(state.get("eval_fixtures")),
        "Eval results:",
        bullet_list(state.get("eval_results")),
        "",
        "## Open Blockers",
        "",
        bullet_list(blockers),
        "",
        "## Last Loop Results",
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
        "## Daemon",
        "",
        f"Enabled: {format_value(daemon.get('enabled'))}",
        f"Status: {format_value(daemon.get('status'))}",
        f"Current role: {current_role(state)}",
        f"Cursor: {format_value(daemon.get('cursor'))}",
        f"Last role: {format_value(daemon.get('last_role'))}",
        "",
        "## Recent Events",
        "",
        "\n".join(
            f"- {event.get('ts', 'TBD')} {event.get('role', 'TBD')}: {event.get('event', 'TBD')} {event.get('note', '')}".strip()
            for event in events
        )
        if events
        else "- TBD",
        "",
    ]
    return "\n".join(lines)


def write_report(state: dict[str, Any], path: Path, digest: str, status: str) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "id": f"{compact_ts()}-operating-dashboard",
        "role": "operating-dashboard",
        "status": "completed",
        "verdict": status,
        "summary": f"Operating dashboard {status}: {path}",
        "created_at": now(),
        "path": str(path),
        "sha256": digest,
    }
    report_path = reports_dir / f"{report['id']}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state.setdefault("structured_reports", []).append(str(report_path.relative_to(ROOT)))
    return report_path


def dashboard_path(raw_path: str) -> Path:
    if not raw_path:
        return DEFAULT_DASHBOARD
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return ROOT / path


def run_dashboard(args: argparse.Namespace) -> tuple[str, Path, str, str]:
    state = load_state()
    dashboard_state = get_obj(state, "operating_dashboard")
    generated_at = str(dashboard_state.get("last_rendered_at") or "TBD") if args.check else now()
    if not args.check and not args.dry_run:
        log_event("synced", str(dashboard_path(args.path)))
    dashboard = render_dashboard(state, args.events, generated_at)
    digest = sha256_text(dashboard)
    path = dashboard_path(args.path)
    current = path.read_text() if path.exists() else ""
    is_current = current == dashboard

    if args.dry_run:
        print(dashboard)
        return "DRY_RUN", path, digest, ""

    if args.check:
        status = "PASS" if is_current else "STALE"
        if args.write_report:
            report_path = write_report(state, path, digest, status)
            state.setdefault("operating_dashboard", {})["last_report"] = str(
                report_path.relative_to(ROOT)
            )
            save_state(state)
            log_event(status, str(path))
        return status, path, digest, "up to date" if is_current else "dashboard is stale or missing"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dashboard)
    status = "PASS"
    state["operating_dashboard"] = {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "last_rendered_at": generated_at,
        "sha256": digest,
        "status": "synced",
        "last_report": state.get("operating_dashboard", {}).get("last_report", "TBD")
        if isinstance(state.get("operating_dashboard"), dict)
        else "TBD",
    }
    if args.write_report:
        report_path = write_report(state, path, digest, status)
        state["operating_dashboard"]["last_report"] = str(report_path.relative_to(ROOT))
    save_state(state)
    return status, path, digest, ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        default="",
        help="Dashboard path. Defaults to orchestration/operating-dashboard.md.",
    )
    parser.add_argument("--events", type=int, default=8, help="Number of recent events to include.")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="Fail if the dashboard is stale or missing."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print dashboard markdown instead of writing it."
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    status, path, digest, message = run_dashboard(args)
    if args.json:
        print(
            json.dumps(
                {"status": status, "path": str(path), "sha256": digest, "message": message},
                indent=2,
                sort_keys=True,
            )
        )
    elif not args.dry_run:
        print(f"Operating dashboard {status}: {path}")
        if message:
            print(message)
    return 0 if status in {"PASS", "DRY_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
