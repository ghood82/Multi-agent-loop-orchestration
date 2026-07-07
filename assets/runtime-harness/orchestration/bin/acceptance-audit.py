#!/usr/bin/env python3
"""Audit whether this harness satisfies the multi-agent operating contract."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"

REQUIRED_ROLES = [
    "builder",
    "qa",
    "security",
    "eval-builder",
    "eval",
    "watchdog",
    "architect",
    "docs",
]

ROLE_RUNNERS = {
    "builder": "bin/run-builder.sh",
    "qa": "bin/run-qa.sh",
    "security": "bin/run-security.sh",
    "eval-builder": "bin/run-eval-builder.sh",
    "eval": "bin/run-eval.sh",
    "watchdog": "bin/run-watchdog.sh",
    "architect": "bin/run-architect.sh",
    "docs": "bin/run-docs.sh",
    "remediation": "bin/run-remediation.sh",
}

REQUIRED_CONTROL_SCRIPTS = [
    "bin/health-check.py",
    "bin/agent-adapter.py",
    "bin/configure-agent-provider.py",
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
    "bin/run-cycle.py",
    "bin/orchestration-daemon.py",
    "bin/setup-intake.py",
    "bin/update-state.py",
    "bin/configure-project.py",
    "bin/normalize-report.py",
    "bin/guard-files.py",
    "bin/release-gate.py",
    "bin/phase-gate.py",
    "bin/resume-plan.py",
    "bin/watch-ci.py",
    "bin/dispatch-subagents.py",
    "bin/acceptance-audit.py",
]

REQUIRED_STATE_FIELDS = [
    "write_lock",
    "agent_adapter",
    "agent_runs",
    "phase_gate",
    "blocking_policy",
    "operating_policy",
    "watchdog",
    "ci_status",
    "release_gate",
    "health_check",
    "operator_status",
    "doctor",
    "requirements_matrix",
    "operating_dashboard",
    "ops_check",
    "policy_audit",
    "setup_intake",
    "resume_plan",
    "daemon",
    "human_approval_required",
    "eval_fixtures",
    "last_eval_fixture",
    "eval_results",
    "last_eval_result_artifact",
    "open_blockers",
    "structured_reports",
    "state_doc",
    "handoff_packets",
    "stop_reports",
    "approval_requests",
]

REQUIRED_STOP_REASONS = [
    "security/privacy risk",
    "schema migration",
    "auth changes",
    "external model behavior",
    "preserved-component removal",
    "API compatibility risk",
    "product judgment",
    "repeated test failures",
    "process drift",
    "unclear requirements",
]

REQUIRED_DOC_PHRASES = [
    "only one loop writes production code at a time",
    "Human Product Owner",
    "Watchdog",
    "release gate",
    "resume-plan",
    "health-check",
    "agent-adapter",
    "doctor",
    "requirements-matrix",
    "status.py",
    "subagents",
    "blockers",
]


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
    entry = {"ts": now(), "role": "acceptance-audit", "event": event, "note": note}
    with (ROOT / "events.log").open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def ok(name: str, evidence: str) -> dict[str, Any]:
    return {"name": name, "status": "PASS", "evidence": evidence, "missing": []}


def fail(name: str, evidence: str, missing: list[str]) -> dict[str, Any]:
    return {"name": name, "status": "FAIL", "evidence": evidence, "missing": missing}


def check_files() -> dict[str, Any]:
    required = list(ROLE_RUNNERS.values()) + REQUIRED_CONTROL_SCRIPTS
    missing = [path for path in required if not (ROOT / path).is_file()]
    if missing:
        return fail("runtime scripts", "Required role/control scripts must exist.", missing)
    return ok("runtime scripts", f"{len(required)} required scripts present.")


def check_state_fields(state: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_STATE_FIELDS if field not in state]
    if missing:
        return fail("state contract", "state.json must expose core control-plane fields.", missing)
    return ok("state contract", "Core control-plane state fields are present.")


def check_roles(state: dict[str, Any]) -> dict[str, Any]:
    daemon = state.get("daemon") if isinstance(state.get("daemon"), dict) else {}
    queue = daemon.get("queue") or []
    missing = [role for role in REQUIRED_ROLES if role not in queue]
    if missing:
        return fail("role sequence", "daemon.queue must include the required orchestration loops.", missing)
    return ok("role sequence", "Daemon queue includes Builder, QA, Security, Eval Builder, Eval, Watchdog, Architect, and Docs.")


def check_write_lock(state: dict[str, Any]) -> dict[str, Any]:
    write_lock = state.get("write_lock") if isinstance(state.get("write_lock"), dict) else {}
    owner = str(write_lock.get("owner", "")).lower()
    missing = []
    if owner != "builder":
        missing.append("write_lock.owner must default to Builder")
    if "allowed_files" not in write_lock:
        missing.append("write_lock.allowed_files")
    if "forbidden_files" not in write_lock:
        missing.append("write_lock.forbidden_files")
    if missing:
        return fail("single-writer lock", "Builder must own production-code write authority by default.", missing)
    return ok("single-writer lock", "Builder owns the default write lock and file scopes are represented.")


def check_blocking_policy(state: dict[str, Any]) -> dict[str, Any]:
    policy = state.get("blocking_policy") if isinstance(state.get("blocking_policy"), dict) else {}
    stop_reasons = policy.get("stop_immediately_for") or []
    missing = [reason for reason in REQUIRED_STOP_REASONS if reason not in stop_reasons]
    if missing:
        return fail("blocking policy", "Global stop conditions must be encoded in state.", missing)
    return ok("blocking policy", "Global stop conditions are encoded in blocking_policy.stop_immediately_for.")


def check_gates(state: dict[str, Any]) -> dict[str, Any]:
    missing = []
    watchdog = state.get("watchdog") if isinstance(state.get("watchdog"), dict) else {}
    if watchdog.get("required") is not True:
        missing.append("watchdog.required true")
    if "release_gate" not in state:
        missing.append("release_gate")
    if "human_approval_required" not in state:
        missing.append("human_approval_required")
    if "ci_status" not in state:
        missing.append("ci_status")
    if missing:
        return fail("gate contract", "Watchdog, release, CI, and human approval gates must be represented.", missing)
    return ok("gate contract", "Watchdog, release, CI, and human approval gates are represented.")


def check_docs() -> dict[str, Any]:
    docs = []
    for path in [ROOT / "README.md", ROOT / "tasks.md"]:
        if path.exists():
            docs.append(path.read_text())
    text = "\n".join(docs).lower()
    missing = [phrase for phrase in REQUIRED_DOC_PHRASES if phrase.lower() not in text]
    if missing:
        return fail("operator documentation", "Skill docs must explain core operating concepts.", missing)
    return ok("operator documentation", "README/SKILL docs cover core operating concepts.")


def build_report() -> dict[str, Any]:
    state = load_state()
    checks = [
        check_files(),
        check_state_fields(state),
        check_roles(state),
        check_write_lock(state),
        check_blocking_policy(state),
        check_gates(state),
        check_docs(),
    ]
    failed = [check for check in checks if check["status"] != "PASS"]
    verdict = "PASS" if not failed else "FAIL"
    return {
        "id": f"{compact_ts()}-acceptance-audit",
        "role": "acceptance-audit",
        "status": "completed",
        "verdict": verdict,
        "summary": "Multi-agent orchestration acceptance audit completed.",
        "created_at": now(),
        "checks": checks,
        "failures": failed,
        "harness_root": str(ROOT),
    }


def write_report(state: dict[str, Any], report: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state.setdefault("structured_reports", []).append(str(path.relative_to(ROOT)))
    state["acceptance_audit"] = {
        "last_decision": report["verdict"],
        "last_checked_at": report["created_at"],
        "last_report": str(path.relative_to(ROOT)),
        "failures": report["failures"],
    }
    save_state(state)
    log_event(report["verdict"], str(path.relative_to(ROOT)))
    return path


def print_summary(report: dict[str, Any], report_path: Path | None) -> None:
    print(f"Acceptance audit: {report['verdict']}")
    if report_path:
        print(f"Report: {report_path}")
    for check in report["checks"]:
        print(f"- {check['status']} {check['name']}: {check['evidence']}")
        for item in check.get("missing") or []:
            print(f"  missing: {item}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true", help="Write audit report and update state.json.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a text summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report()
    report_path = write_report(load_state(), report) if args.write_report else None
    if args.json:
        output = dict(report)
        if report_path:
            output["report_path"] = str(report_path)
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print_summary(report, report_path)
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
