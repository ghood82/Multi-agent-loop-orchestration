#!/usr/bin/env python3
"""Decide whether the current roadmap phase may advance."""

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
PASS_VALUES = {"PASS", "PASSED", "APPROVE", "APPROVED", "COMPLETE", "COMPLETED", "READY", "DONE"}
ARCHITECT_PASS_VALUES = PASS_VALUES | {"ADVANCE", "PHASE_COMPLETE", "PHASE COMPLETE"}
APPROVED = {"approved"}


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


def log_event(event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": "phase-gate", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def norm(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_")


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


def approval_exists(state: dict[str, Any]) -> bool:
    for ref in state.get("human_approvals") or []:
        path = ROOT / str(ref)
        if not path.exists():
            path = ROOT / "approvals" / Path(str(ref)).name
        if not path.exists():
            continue
        try:
            approval = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if str(approval.get("decision", "")).lower() in APPROVED:
            return True
    return False


def security_required(args: argparse.Namespace, state: dict[str, Any]) -> bool:
    if args.require_security:
        return True
    if args.skip_security:
        return False
    high_risk = state.get("high_risk_areas") or []
    if isinstance(high_risk, list) and high_risk:
        return True
    phase_gate = state.get("phase_gate") if isinstance(state.get("phase_gate"), dict) else {}
    requirements = " ".join(
        str(item).lower() for item in phase_gate.get("next_phase_requires") or []
    )
    return "security" in requirements


def check(name: str, required: bool, passed: bool, evidence: str, missing: str) -> dict[str, Any]:
    status = "NOT_REQUIRED" if not required else "PASS" if passed else "BLOCKING"
    return {
        "name": name,
        "required": required,
        "status": status,
        "evidence": evidence or "missing",
        "missing": "" if status != "BLOCKING" else missing,
    }


def build_report(args: argparse.Namespace, state: dict[str, Any]) -> dict[str, Any]:
    phase_gate = state.get("phase_gate") if isinstance(state.get("phase_gate"), dict) else {}
    watchdog = state.get("watchdog") if isinstance(state.get("watchdog"), dict) else {}
    policy_audit = state.get("policy_audit") if isinstance(state.get("policy_audit"), dict) else {}
    blockers = open_blockers(state)
    require_human = args.require_human_approval or bool(state.get("human_approval_required"))

    checks = [
        check(
            "open_blockers",
            True,
            not blockers,
            f"{len(blockers)} open blocker(s)",
            "Resolve open blockers before phase advancement.",
        ),
        check(
            "qa_pass",
            True,
            norm(state.get("last_qa_result")) in PASS_VALUES,
            str(state.get("last_qa_result") or "missing"),
            "QA / Verification must pass or approve the phase.",
        ),
        check(
            "security_pass",
            security_required(args, state),
            norm(state.get("last_security_result")) in PASS_VALUES,
            str(state.get("last_security_result") or "missing"),
            "Security / Privacy must pass because this phase is high-risk or security-gated.",
        ),
        check(
            "eval_pass",
            True,
            norm(state.get("last_eval_result")) in PASS_VALUES,
            str(state.get("last_eval_result") or "missing"),
            "Eval Monitor must record a PASS result.",
        ),
        check(
            "watchdog_pass",
            True,
            norm(watchdog.get("last_verdict") or state.get("last_watchdog_verdict")) in PASS_VALUES,
            str(watchdog.get("last_verdict") or state.get("last_watchdog_verdict") or "missing"),
            "Watchdog must return PASS.",
        ),
        check(
            "architect_approval",
            True,
            norm(state.get("last_architect_decision")) in ARCHITECT_PASS_VALUES,
            str(state.get("last_architect_decision") or "missing"),
            "Architect / Release Manager must approve phase completion.",
        ),
        check(
            "policy_audit_pass",
            not args.skip_policy_audit,
            norm(policy_audit.get("last_decision")) == "PASS",
            str(policy_audit.get("last_decision") or "missing"),
            "Policy audit must pass for selected operating policy.",
        ),
        check(
            "human_approval",
            require_human,
            approval_exists(state),
            "approved" if approval_exists(state) else "missing",
            "Human Product Owner approval is required before phase advancement.",
        ),
    ]
    blocking = [item for item in checks if item["status"] == "BLOCKING"]
    decision = "PASS" if not blocking else "STOP"
    return {
        "id": f"{compact_ts()}-phase-gate",
        "role": "phase-gate",
        "status": "completed",
        "verdict": decision,
        "summary": f"Phase gate decision: {decision}",
        "created_at": now(),
        "current_phase": state.get("current_phase", "TBD"),
        "authorized_phase": phase_gate.get("authorized_phase", state.get("current_phase", "TBD")),
        "requested_next_phase": args.advance_to or "",
        "checks": checks,
        "blocking": blocking,
        "warnings": [],
        "recommended_next_action": (
            f"Advance to {args.advance_to}."
            if decision == "PASS" and args.advance_to
            else "Current phase may be marked complete."
            if decision == "PASS"
            else f"Resolve blocking phase gate checks: {', '.join(item['name'] for item in blocking)}."
        ),
    }


def write_report(state: dict[str, Any], report: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state.setdefault("structured_reports", []).append(str(path.relative_to(ROOT)))
    state.setdefault("phase_gate", {})["last_decision"] = report["verdict"]
    state["phase_gate"]["last_checked_at"] = report["created_at"]
    state["phase_gate"]["last_report"] = str(path.relative_to(ROOT))
    state["phase_gate"]["blocking"] = report["blocking"]
    state["phase_gate"]["warnings"] = report["warnings"]
    if report["verdict"] == "PASS" and report.get("requested_next_phase"):
        next_phase = report["requested_next_phase"]
        state["current_phase"] = next_phase
        state["phase_gate"]["authorized_phase"] = next_phase
        state["write_lock"]["scope"] = next_phase
        state["next_authorized_action"] = f"Architect assigns Builder task for {next_phase}"
    save_state(state)
    log_event(report["verdict"], str(path.relative_to(ROOT)))
    return path


def maybe_open_blocker(state: dict[str, Any], report: dict[str, Any], report_path: Path) -> None:
    if report["verdict"] == "PASS" or not report["blocking"]:
        return
    state.setdefault("open_blockers", []).append(
        {
            "id": f"blocker-{compact_ts()}",
            "status": "open",
            "severity": "high",
            "owner": "phase-gate",
            "description": f"Phase gate STOP: {report['blocking'][0]['name']}",
            "created_at": now(),
            "evidence": str(report_path.relative_to(ROOT)),
            "recommended_next_action": report["recommended_next_action"],
        }
    )
    save_state(state)


def print_text(report: dict[str, Any]) -> None:
    print(f"Phase gate: {report['verdict']}")
    print(f"Current phase: {report['current_phase']}")
    if report.get("requested_next_phase"):
        print(f"Requested next phase: {report['requested_next_phase']}")
    for item in report["checks"]:
        print(f"- {item['name']}: {item['status']} ({item['evidence']})")
    print(f"Next action: {report['recommended_next_action']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--advance-to", default="", help="Advance current/authorized phase if gate passes."
    )
    parser.add_argument("--require-security", action="store_true")
    parser.add_argument("--skip-security", action="store_true")
    parser.add_argument("--require-human-approval", action="store_true")
    parser.add_argument("--skip-policy-audit", action="store_true")
    parser.add_argument("--open-blocker", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict", action="store_true", help="Return nonzero unless phase gate verdict is PASS."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = load_state()
    report = build_report(args, state)
    report_path: Path | None = None
    if args.write_report or report["verdict"] == "PASS" and args.advance_to:
        report_path = write_report(state, report)
        state = load_state()
    if args.open_blocker and report["verdict"] != "PASS":
        if report_path is None:
            report_path = write_report(state, report)
            state = load_state()
        maybe_open_blocker(state, report, report_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 1 if args.strict and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
