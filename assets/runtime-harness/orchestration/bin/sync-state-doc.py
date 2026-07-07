#!/usr/bin/env python3
"""Render the shared project roadmap state markdown from orchestration state."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
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
    entry = {"ts": now(), "role": "state-doc-sync", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def format_scalar(value: Any) -> str:
    if value is None or value == "":
        return "TBD"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return json.dumps(value, sort_keys=True)


def format_list(value: Any) -> str:
    if not value:
        return "- TBD"
    if not isinstance(value, list):
        return f"- {format_scalar(value)}"
    lines: list[str] = []
    for item in value:
        if isinstance(item, dict):
            label = item.get("description") or item.get("id") or json.dumps(item, sort_keys=True)
            detail = []
            for key in ["status", "severity", "owner", "evidence"]:
                if item.get(key):
                    detail.append(f"{key}: {item[key]}")
            suffix = f" ({'; '.join(detail)})" if detail else ""
            lines.append(f"- {label}{suffix}")
        else:
            lines.append(f"- {format_scalar(item)}")
    return "\n".join(lines)


def get_obj(state: dict[str, Any], key: str) -> dict[str, Any]:
    value = state.get(key)
    return value if isinstance(value, dict) else {}


def render_markdown(state: dict[str, Any]) -> str:
    write_lock = get_obj(state, "write_lock")
    phase_gate = get_obj(state, "phase_gate")
    blocking_policy = get_obj(state, "blocking_policy")
    operating_policy = get_obj(state, "operating_policy")
    watchdog = get_obj(state, "watchdog")
    ci_status = get_obj(state, "ci_status")
    release_gate = get_obj(state, "release_gate")
    health_check = get_obj(state, "health_check")
    acceptance_audit = get_obj(state, "acceptance_audit")
    operator_status = get_obj(state, "operator_status")
    policy_audit = get_obj(state, "policy_audit")
    resume_plan = get_obj(state, "resume_plan")

    lines = [
        "# Project Roadmap State",
        "",
        "> Generated from `orchestration/state.json`. Edit runtime state with `orchestration/bin/update-state.py` or the orchestration scripts, then rerun `python3 orchestration/bin/sync-state-doc.py`.",
        "",
        "## Project",
        "",
        f"Project name: {format_scalar(state.get('project_name'))}",
        f"Repo: {format_scalar(state.get('repo'))}",
        f"Roadmap: {format_scalar(state.get('roadmap'))}",
        f"Current phase: {format_scalar(state.get('current_phase'))}",
        f"Current objective: {format_scalar(state.get('current_objective'))}",
        f"Current active branch: {format_scalar(state.get('active_branch'))}",
        f"Current active PR: {format_scalar(state.get('active_pr'))}",
        f"State file path: {format_scalar(state.get('state_file_path'))}",
        f"Test command: {format_scalar(state.get('test_command'))}",
        f"Operating policy path: {format_scalar(operating_policy.get('path'))}",
        f"Operating policy profile: {format_scalar(operating_policy.get('profile'))}",
        "",
        "## Write Lock",
        "",
        f"Active writer: {format_scalar(state.get('active_writer'))}",
        f"Write lock status: {format_scalar(write_lock.get('status'))}",
        f"Write lock owner: {format_scalar(write_lock.get('owner'))}",
        f"Write lock scope: {format_scalar(write_lock.get('scope'))}",
        "Write lock allowed files:",
        format_list(write_lock.get("allowed_files")),
        "Write lock forbidden files:",
        format_list(write_lock.get("forbidden_files")),
        "",
        "## Phase Gate",
        "",
        f"Authorized phase: {format_scalar(phase_gate.get('authorized_phase'))}",
        f"Phase gate decision: {format_scalar(phase_gate.get('last_decision'))}",
        f"Phase gate checked at: {format_scalar(phase_gate.get('last_checked_at'))}",
        "Unauthorized phases:",
        format_list(phase_gate.get("unauthorized_phases")),
        "Next phase requires:",
        format_list(phase_gate.get("next_phase_requires")),
        "",
        "## Scope Controls",
        "",
        "Allowed files:",
        format_list(state.get("allowed_files")),
        "Forbidden files:",
        format_list(state.get("forbidden_files")),
        "Preserved components:",
        format_list(state.get("preserved_components")),
        "Forbidden changes:",
        format_list(state.get("forbidden_changes")),
        "Controlled taxonomy:",
        format_list(state.get("controlled_taxonomy")),
        "Eval fixtures:",
        format_list(state.get("eval_fixtures")),
        "Eval results:",
        format_list(state.get("eval_results")),
        "",
        "## Blocking Policy",
        "",
        f"Blocker handling mode: {format_scalar(blocking_policy.get('mode'))}",
        f"Blocker recovery limit: {format_scalar(blocking_policy.get('recovery_limit'))}",
        f"Low risk recovery allowed: {format_scalar(blocking_policy.get('low_risk_recovery_allowed'))}",
        "Stop immediately for:",
        format_list(blocking_policy.get("stop_immediately_for")),
        f"Default action: {format_scalar(blocking_policy.get('default_action'))}",
        "",
        "## Risks And Blockers",
        "",
        "Known risks:",
        format_list(state.get("known_risks")),
        "Open blockers:",
        format_list(open_blockers(state)),
        "Resolved blockers:",
        format_list(state.get("resolved_blockers")),
        "",
        "## Gate Status",
        "",
        f"Health check: {format_scalar(health_check.get('last_decision'))}",
        f"Policy audit: {format_scalar(policy_audit.get('last_decision'))}",
        f"Policy audit profile: {format_scalar(policy_audit.get('policy_profile'))}",
        f"Acceptance audit: {format_scalar(acceptance_audit.get('last_decision'))}",
        f"Operator status: {format_scalar(operator_status.get('last_decision'))}",
        f"Watchdog verdict: {format_scalar(watchdog.get('last_verdict', state.get('last_watchdog_verdict')))}",
        f"Watchdog product quality: {format_scalar(watchdog.get('product_quality_status'))}",
        f"Watchdog eval quality: {format_scalar(watchdog.get('eval_quality_status', state.get('eval_quality_status')))}",
        f"Watchdog process integrity: {format_scalar(watchdog.get('process_integrity_status'))}",
        f"CI conclusion: {format_scalar(ci_status.get('conclusion'))}",
        f"CI URL: {format_scalar(ci_status.get('url'))}",
        f"Release gate decision: {format_scalar(release_gate.get('last_decision'))}",
        f"Release gate mode: {format_scalar(release_gate.get('mode'))}",
        f"Human approval required: {format_scalar(state.get('human_approval_required'))}",
        "Human approvals:",
        format_list(state.get("human_approvals")),
        "",
        "## Last Results",
        "",
        f"Last Builder result: {format_scalar(state.get('last_builder_result'))}",
        f"Last QA result: {format_scalar(state.get('last_qa_result'))}",
        f"Last Security result: {format_scalar(state.get('last_security_result'))}",
        f"Last Eval Builder result: {format_scalar(state.get('last_eval_builder_result'))}",
        f"Last Eval result: {format_scalar(state.get('last_eval_result'))}",
        f"Last Eval result artifact: {format_scalar(state.get('last_eval_result_artifact'))}",
        f"Last Watchdog verdict: {format_scalar(state.get('last_watchdog_verdict'))}",
        f"Last Remediation result: {format_scalar(state.get('last_remediation_result'))}",
        f"Last Architect decision: {format_scalar(state.get('last_architect_decision'))}",
        f"Last Documentation update: {format_scalar(state.get('last_documentation_update'))}",
        "",
        "## Resume",
        "",
        f"Resume decision: {format_scalar(resume_plan.get('decision'))}",
        f"Resume next role: {format_scalar(resume_plan.get('next_role'))}",
        f"Resume next action: {format_scalar(resume_plan.get('next_action'))}",
        f"Resume reason: {format_scalar(resume_plan.get('reason'))}",
        f"Next authorized action: {format_scalar(state.get('next_authorized_action'))}",
        "",
    ]
    return "\n".join(lines)


def target_path(state: dict[str, Any], override: str) -> Path:
    raw_path = override or str(state.get("state_file_path") or "docs/project-roadmap-state.md")
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def write_report(
    state: dict[str, Any], status: str, path: Path, digest: str, check_only: bool
) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "id": f"{compact_ts()}-state-doc-sync",
        "role": "state-doc-sync",
        "status": "completed",
        "verdict": status,
        "summary": f"State doc sync {status}: {path}",
        "created_at": now(),
        "path": str(path),
        "sha256": digest,
        "check_only": check_only,
    }
    report_path = reports_dir / f"{report['id']}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state.setdefault("structured_reports", []).append(str(report_path.relative_to(ROOT)))
    return report_path


def sync_state_doc(args: argparse.Namespace) -> tuple[str, Path, str, str]:
    state = load_state()
    markdown = render_markdown(state)
    digest = sha256_text(markdown)
    path = target_path(state, args.path)
    current = path.read_text() if path.exists() else ""
    is_current = current == markdown

    if args.dry_run:
        print(markdown)
        return "DRY_RUN", path, digest, ""

    if args.check:
        status = "PASS" if is_current else "STALE"
        if args.write_report:
            report_path = write_report(state, status, path, digest, True)
            save_state(state)
            log_event(status, str(report_path.relative_to(ROOT)))
        return status, path, digest, "up to date" if is_current else "state doc is stale or missing"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown)
    state["state_doc"] = {
        "path": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
        "last_synced_at": now(),
        "sha256": digest,
        "status": "synced",
    }
    report_note = ""
    if args.write_report:
        report_path = write_report(state, "PASS", path, digest, False)
        report_note = str(report_path.relative_to(ROOT))
    save_state(state)
    log_event("synced", str(path))
    return "PASS", path, digest, report_note


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default="", help="Override the target markdown path.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Return nonzero if the markdown file is missing or stale.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print markdown without writing files."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON status.")
    parser.add_argument(
        "--write-report", action="store_true", help="Write a structured sync report."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    status, path, digest, note = sync_state_doc(args)
    output = {
        "status": status,
        "path": str(path),
        "sha256": digest,
        "note": note,
    }
    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"State doc sync: {status}")
        print(f"Path: {path}")
        if note:
            print(f"Note: {note}")
    if args.check and status != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
