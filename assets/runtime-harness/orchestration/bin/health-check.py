#!/usr/bin/env python3
"""Validate the local orchestration harness before starting autonomous loops."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"

REQUIRED_FILES = [
    "state.json",
    "agent-adapter.json",
    "operating-policy.json",
    "README.md",
    "events.log",
    "tasks.md",
    "locks/production-code.lock",
    "subagents/manifest.json",
    "schemas/state.schema.json",
    "schemas/report.schema.json",
    "schemas/blocker.schema.json",
    "schemas/approval.schema.json",
    "bin/common.sh",
    "bin/agent-adapter.py",
    "bin/configure-agent-provider.py",
    "bin/setup-intake.py",
    "bin/update-state.py",
    "bin/configure-project.py",
    "bin/normalize-report.py",
    "bin/guard-files.py",
    "bin/release-gate.py",
    "bin/phase-gate.py",
    "bin/resume-plan.py",
    "bin/doctor.py",
    "bin/requirements-matrix.py",
    "bin/status.py",
    "bin/operating-dashboard.py",
    "bin/ops-check.py",
    "bin/policy-audit.py",
    "bin/sync-state-doc.py",
    "bin/eval-fixture.py",
    "bin/eval-result.py",
    "bin/handoff-packet.py",
    "bin/stop-report.py",
    "bin/approval-request.py",
    "bin/watch-ci.py",
    "bin/dispatch-subagents.py",
    "bin/acceptance-audit.py",
    "bin/run-cycle.py",
    "bin/orchestration-daemon.py",
]

REQUIRED_DIRS = [
    "approvals",
    "guards",
    "locks",
    "reports/agent-runs",
    "reports/json",
    "evals/fixtures",
    "evals/results",
    "schemas",
    "subagents",
    "worktrees",
]

EXECUTABLE_FILES = [
    "bin/update-state.py",
    "bin/agent-adapter.py",
    "bin/configure-agent-provider.py",
    "bin/setup-intake.py",
    "bin/configure-project.py",
    "bin/normalize-report.py",
    "bin/guard-files.py",
    "bin/release-gate.py",
    "bin/phase-gate.py",
    "bin/resume-plan.py",
    "bin/doctor.py",
    "bin/requirements-matrix.py",
    "bin/status.py",
    "bin/operating-dashboard.py",
    "bin/ops-check.py",
    "bin/policy-audit.py",
    "bin/sync-state-doc.py",
    "bin/eval-fixture.py",
    "bin/eval-result.py",
    "bin/handoff-packet.py",
    "bin/stop-report.py",
    "bin/approval-request.py",
    "bin/watch-ci.py",
    "bin/dispatch-subagents.py",
    "bin/acceptance-audit.py",
    "bin/run-cycle.py",
    "bin/orchestration-daemon.py",
    "bin/run-builder.sh",
    "bin/run-qa.sh",
    "bin/run-security.sh",
    "bin/run-eval-builder.sh",
    "bin/run-eval.sh",
    "bin/run-watchdog.sh",
    "bin/run-architect.sh",
    "bin/run-docs.sh",
    "bin/run-remediation.sh",
]

JSON_FILES = [
    "state.json",
    "agent-adapter.json",
    "operating-policy.json",
    "subagents/manifest.json",
    "schemas/state.schema.json",
    "schemas/report.schema.json",
    "schemas/blocker.schema.json",
    "schemas/approval.schema.json",
]

REQUIRED_STATE_KEYS = [
    "project_name",
    "repo",
    "roadmap",
    "current_phase",
    "current_objective",
    "agent_adapter",
    "agent_runs",
    "daemon",
    "write_lock",
    "phase_gate",
    "operating_policy",
    "doctor",
    "requirements_matrix",
    "operating_dashboard",
    "ops_check",
    "policy_audit",
    "setup_intake",
    "eval_fixtures",
    "eval_results",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def load_json(path: Path) -> tuple[Any | None, str]:
    try:
        return json.loads(path.read_text()), ""
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def load_state() -> dict[str, Any]:
    state, error = load_json(STATE_FILE)
    if error:
        return {}
    if not isinstance(state, dict):
        return {}
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(event: str, note: str) -> None:
    entry = {"ts": now(), "role": "health-check", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def append_issue(issues: list[str], rel_path: str, message: str) -> None:
    issues.append(f"{rel_path}: {message}")


def check_git_repo(warnings: list[str]) -> dict[str, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        warnings.append(f"git unavailable: {exc}")
        return {"available": "false", "root": "", "error": str(exc)}

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "not a git repository").strip()
        warnings.append(f"git repo check did not pass: {message}")
        return {"available": "false", "root": "", "error": message}

    return {"available": "true", "root": result.stdout.strip(), "error": ""}


def unresolved_blockers(state: dict[str, Any]) -> list[Any]:
    blockers = state.get("open_blockers") or []
    if not isinstance(blockers, list):
        return [blockers]
    return [
        blocker
        for blocker in blockers
        if not isinstance(blocker, dict) or blocker.get("status", "open") not in {"resolved", "closed"}
    ]


def latest_status(state: dict[str, Any]) -> dict[str, Any]:
    watchdog = state.get("watchdog") if isinstance(state.get("watchdog"), dict) else {}
    ci_status = state.get("ci_status") if isinstance(state.get("ci_status"), dict) else {}
    release_gate = state.get("release_gate") if isinstance(state.get("release_gate"), dict) else {}
    daemon = state.get("daemon") if isinstance(state.get("daemon"), dict) else {}
    return {
        "open_blockers": len(unresolved_blockers(state)),
        "watchdog_verdict": watchdog.get("last_verdict", state.get("last_watchdog_verdict", "TBD")),
        "ci_conclusion": ci_status.get("conclusion", "TBD"),
        "release_gate_decision": release_gate.get("last_decision", "TBD"),
        "daemon_status": daemon.get("status", "TBD"),
        "daemon_cursor": daemon.get("cursor", "TBD"),
        "next_authorized_action": state.get("next_authorized_action", "TBD"),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    parsed_json: dict[str, str] = {}

    for rel_path in REQUIRED_FILES:
        path = ROOT / rel_path
        if not path.is_file():
            append_issue(failures, rel_path, "required file missing")

    for rel_path in REQUIRED_DIRS:
        path = ROOT / rel_path
        if not path.is_dir():
            append_issue(failures, rel_path, "required directory missing")

    for rel_path in EXECUTABLE_FILES:
        path = ROOT / rel_path
        if path.exists() and not os.access(path, os.X_OK):
            append_issue(warnings, rel_path, "file is not executable")

    json_objects: dict[str, Any] = {}
    for rel_path in JSON_FILES:
        data, error = load_json(ROOT / rel_path)
        if error:
            append_issue(failures, rel_path, error)
            parsed_json[rel_path] = "FAIL"
        else:
            json_objects[rel_path] = data
            parsed_json[rel_path] = "PASS"

    state = json_objects.get("state.json")
    if isinstance(state, dict):
        for key in REQUIRED_STATE_KEYS:
            if key not in state:
                append_issue(failures, "state.json", f"missing required key: {key}")
    elif "state.json" not in parsed_json:
        append_issue(failures, "state.json", "state did not parse as an object")

    manifest = json_objects.get("subagents/manifest.json")
    if isinstance(manifest, dict):
        subagents = manifest.get("subagents")
        if not isinstance(subagents, list) or not subagents:
            append_issue(warnings, "subagents/manifest.json", "no subagents configured")

    git_status = check_git_repo(warnings)

    if args.require_agent_command and not os.environ.get("AGENT_COMMAND"):
        warnings.append("AGENT_COMMAND is not set; runners will only prepare prompts unless an agent command is provided.")

    state_for_status = state if isinstance(state, dict) else {}
    status_snapshot = latest_status(state_for_status)
    if status_snapshot["open_blockers"]:
        warnings.append(f"{status_snapshot['open_blockers']} open blocker(s) are present.")

    decision = "FAIL" if failures else "WARN" if warnings else "PASS"
    return {
        "id": f"{compact_ts()}-health-check",
        "role": "health-check",
        "status": "complete",
        "verdict": decision,
        "summary": "Harness health check completed.",
        "created_at": now(),
        "harness_root": str(ROOT),
        "repo_root": str(REPO_ROOT),
        "failures": failures,
        "warnings": warnings,
        "parsed_json": parsed_json,
        "git": git_status,
        "status_snapshot": status_snapshot,
        "strict": args.strict,
        "require_agent_command": args.require_agent_command,
    }


def write_report(report: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{report['id']}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    state = load_state()
    if state:
        state["health_check"] = {
            "last_decision": report["verdict"],
            "last_checked_at": report["created_at"],
            "last_report": str(report_path.relative_to(ROOT)),
            "failures": report["failures"],
            "warnings": report["warnings"],
        }
        state.setdefault("structured_reports", []).append(str(report_path.relative_to(ROOT)))
        save_state(state)
    log_event(report["verdict"], str(report_path.relative_to(ROOT)))
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero for warnings as well as failures.",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write the health report and update state.json.",
    )
    parser.add_argument(
        "--require-agent-command",
        action="store_true",
        help="Warn when AGENT_COMMAND is unset.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact text summary instead of JSON.",
    )
    return parser.parse_args()


def print_summary(report: dict[str, Any], report_path: Path | None) -> None:
    print(f"Health check: {report['verdict']}")
    print(f"Harness: {report['harness_root']}")
    if report_path:
        print(f"Report: {report_path}")
    if report["failures"]:
        print("Failures:")
        for item in report["failures"]:
            print(f"- {item}")
    if report["warnings"]:
        print("Warnings:")
        for item in report["warnings"]:
            print(f"- {item}")


def main() -> int:
    args = parse_args()
    report = build_report(args)
    report_path = write_report(report) if args.write_report else None

    if args.summary:
        print_summary(report, report_path)
    else:
        output = dict(report)
        if report_path:
            output["report_path"] = str(report_path)
        print(json.dumps(output, indent=2, sort_keys=True))

    if report["verdict"] == "FAIL":
        return 2
    if args.strict and report["verdict"] == "WARN":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
