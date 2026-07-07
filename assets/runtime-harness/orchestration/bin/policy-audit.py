#!/usr/bin/env python3
"""Audit the active operating policy and the evidence required by its gates."""

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
APPROVED = {"approved"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid {label} JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must contain a JSON object: {path}")
    return value


def load_state() -> dict[str, Any]:
    return load_json(STATE_FILE, "state")


def load_policy(args: argparse.Namespace, state: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    configured = (
        state.get("operating_policy") if isinstance(state.get("operating_policy"), dict) else {}
    )
    policy_path = Path(args.policy or configured.get("path") or "operating-policy.json")
    if not policy_path.is_absolute():
        policy_path = ROOT / policy_path
    return load_json(policy_path, "operating policy"), policy_path


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": "policy-audit", "event": event, "note": note}
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


def latest_watchdog(state: dict[str, Any]) -> str:
    watchdog = state.get("watchdog") if isinstance(state.get("watchdog"), dict) else {}
    return (
        str(watchdog.get("last_verdict") or state.get("last_watchdog_verdict") or "")
        .strip()
        .upper()
    )


def latest_eval(state: dict[str, Any]) -> str:
    result = state.get("last_eval_result")
    if isinstance(result, str) and result.strip() and result.upper() not in {"TBD", "NONE", "N/A"}:
        return result.strip().upper()
    refs = state.get("eval_results") or []
    if not isinstance(refs, list) or not refs:
        return ""
    path = ROOT / str(refs[-1])
    if not path.exists():
        path = ROOT / "evals" / "results" / Path(str(refs[-1])).name
    if not path.exists():
        return ""
    try:
        latest = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ""
    return str(latest.get("verdict", "")).strip().upper()


def ci_conclusion(state: dict[str, Any]) -> str:
    ci_status = state.get("ci_status") if isinstance(state.get("ci_status"), dict) else {}
    return str(ci_status.get("conclusion", "")).strip().lower()


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


def file_guard_violations(state: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for check in state.get("file_guard_checks") or []:
        if not isinstance(check, dict):
            continue
        for violation in check.get("violations") or []:
            violations.append(str(violation))
    return violations


def classify_policy(policy: dict[str, Any]) -> str:
    profile = str(policy.get("profile") or "").strip().lower()
    if profile:
        return profile
    gates = policy.get("gates") if isinstance(policy.get("gates"), dict) else {}
    run_cycle = policy.get("run_cycle") if isinstance(policy.get("run_cycle"), dict) else {}
    strict_signals = [
        gates.get("require_latest_eval_pass"),
        gates.get("require_ci_pass"),
        gates.get("require_human_approval"),
        gates.get("strict_file_guard"),
        run_cycle.get("strict_gates"),
        run_cycle.get("release_gate"),
    ]
    return "strict" if any(strict_signals) else "standard"


def check_gate(
    name: str, required: bool, passed: bool, evidence: str, missing: str
) -> dict[str, Any]:
    if not required:
        status = "NOT_REQUIRED"
    elif passed:
        status = "PASS"
    else:
        status = "MISSING"
    return {
        "name": name,
        "required": required,
        "status": status,
        "evidence": evidence,
        "missing": "" if status != "MISSING" else missing,
    }


def build_audit(state: dict[str, Any], policy: dict[str, Any], policy_path: Path) -> dict[str, Any]:
    gates = policy.get("gates") if isinstance(policy.get("gates"), dict) else {}
    run_cycle = policy.get("run_cycle") if isinstance(policy.get("run_cycle"), dict) else {}
    blockers = open_blockers(state)
    watchdog = latest_watchdog(state)
    eval_result = latest_eval(state)
    ci = ci_conclusion(state)
    approvals = approval_exists(state)
    guard_violations = file_guard_violations(state)

    gate_checks = [
        check_gate(
            "watchdog_pass",
            gates.get("require_watchdog_pass", True) is not False,
            watchdog == "PASS",
            watchdog or "missing",
            "Run Watchdog and record a PASS verdict.",
        ),
        check_gate(
            "latest_eval_pass",
            bool(gates.get("require_latest_eval_pass")),
            eval_result == "PASS",
            eval_result or "missing",
            "Run Eval Monitor and record a PASS eval result.",
        ),
        check_gate(
            "ci_pass",
            bool(gates.get("require_ci_pass")),
            ci in PASS_CI,
            ci or "missing",
            "Refresh CI and resolve failures until the conclusion is passing.",
        ),
        check_gate(
            "human_approval",
            bool(gates.get("require_human_approval")),
            approvals,
            "approved" if approvals else "missing",
            "Record an approved Human Product Owner artifact.",
        ),
        check_gate(
            "strict_file_guard",
            bool(gates.get("strict_file_guard")),
            not guard_violations,
            f"{len(guard_violations)} violation(s)",
            "Resolve or justify recorded file-guard violations.",
        ),
    ]
    if blockers:
        gate_checks.append(
            {
                "name": "open_blockers",
                "required": True,
                "status": "MISSING",
                "evidence": f"{len(blockers)} open blocker(s)",
                "missing": "Resolve open blockers or route them through Blocker Remediation.",
            }
        )

    missing = [gate for gate in gate_checks if gate["status"] == "MISSING"]
    mode = classify_policy(policy)
    verdict = "PASS" if not missing else "FAIL"
    return {
        "id": f"{compact_ts()}-policy-audit",
        "role": "policy-audit",
        "status": "completed",
        "verdict": verdict,
        "summary": f"Operating policy audit {verdict} for profile {mode}.",
        "created_at": now(),
        "policy_path": str(policy_path.relative_to(ROOT))
        if policy_path.is_relative_to(ROOT)
        else str(policy_path),
        "policy_profile": mode,
        "gates": gates,
        "run_cycle": run_cycle,
        "checks": gate_checks,
        "missing_evidence": missing,
        "recommended_next_action": (
            "Policy evidence is complete for the selected gates."
            if not missing
            else f"Address missing gate evidence: {', '.join(gate['name'] for gate in missing)}."
        ),
    }


def write_report(state: dict[str, Any], report: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state.setdefault("structured_reports", []).append(str(path.relative_to(ROOT)))
    state["policy_audit"] = {
        "last_decision": report["verdict"],
        "last_checked_at": report["created_at"],
        "last_report": str(path.relative_to(ROOT)),
        "policy_profile": report["policy_profile"],
        "missing_evidence": report["missing_evidence"],
    }
    save_state(state)
    log_event(report["verdict"], str(path.relative_to(ROOT)))
    return path


def print_text(report: dict[str, Any]) -> None:
    print(f"Policy audit: {report['verdict']}")
    print(f"Profile: {report['policy_profile']}")
    print(f"Policy path: {report['policy_path']}")
    print("Gate checks:")
    for check in report["checks"]:
        print(f"- {check['name']}: {check['status']} ({check['evidence']})")
    print(f"Next action: {report['recommended_next_action']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        default="",
        help="Policy path. Defaults to state.operating_policy.path or operating-policy.json.",
    )
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict", action="store_true", help="Return nonzero unless policy audit verdict is PASS."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = load_state()
    policy, policy_path = load_policy(args, state)
    report = build_audit(state, policy, policy_path)
    if args.write_report:
        write_report(state, report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 1 if args.strict and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
