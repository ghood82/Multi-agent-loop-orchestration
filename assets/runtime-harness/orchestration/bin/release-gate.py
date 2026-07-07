#!/usr/bin/env python3
"""Decide whether an orchestration run may advance toward PR, merge, or release."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"
DEFAULT_POLICY_FILE = ROOT / "operating-policy.json"

PASS_CI = {"success", "succeeded", "passed", "pass", "green"}
APPROVED = {"approved"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate release readiness from orchestration state.")
    parser.add_argument("--mode", choices=["status", "pr", "merge", "release"], default="status")
    parser.add_argument("--pr", default="", help="PR number, URL, or branch for GitHub CLI lookup.")
    parser.add_argument("--pr-from-file", default="", help="Read gh pr view JSON from a file.")
    parser.add_argument("--require-ci-pass", action="store_true")
    parser.add_argument("--require-human-approval", action="store_true")
    parser.add_argument("--require-watchdog-pass", action="store_true", default=True)
    parser.add_argument("--require-latest-eval-pass", action="store_true")
    parser.add_argument("--allow-draft-pr", action="store_true")
    parser.add_argument("--allow-review-pending", action="store_true")
    parser.add_argument("--strict-file-guard", action="store_true")
    parser.add_argument("--policy", default="operating-policy.json", help="Operating policy JSON path, relative to orchestration root unless absolute.")
    parser.add_argument("--no-policy", action="store_true", help="Ignore operating-policy.json defaults for this run.")
    parser.add_argument("--open-blocker", action="store_true")
    return parser.parse_args()


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON: {exc}") from exc


def load_policy(args: argparse.Namespace) -> dict[str, Any]:
    if args.no_policy:
        return {}
    path = Path(args.policy)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {}
    try:
        policy = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid operating policy JSON: {path}: {exc}") from exc
    if not isinstance(policy, dict):
        raise SystemExit(f"Operating policy must contain a JSON object: {path}")
    return policy


def policy_gates(policy: dict[str, Any]) -> dict[str, Any]:
    gates = policy.get("gates")
    return gates if isinstance(gates, dict) else {}


def apply_policy(args: argparse.Namespace, policy: dict[str, Any]) -> None:
    gates = policy_gates(policy)
    args.require_ci_pass = args.require_ci_pass or bool(gates.get("require_ci_pass"))
    args.require_human_approval = args.require_human_approval or bool(gates.get("require_human_approval"))
    args.require_latest_eval_pass = args.require_latest_eval_pass or bool(gates.get("require_latest_eval_pass"))
    args.strict_file_guard = args.strict_file_guard or bool(gates.get("strict_file_guard"))
    if gates.get("require_watchdog_pass") is False:
        args.require_watchdog_pass = False


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
        if not isinstance(blocker, dict) or blocker.get("status", "open") not in {"resolved", "closed"}
    ]


def latest_watchdog(state: dict[str, Any]) -> str:
    verdict = state.get("watchdog", {}).get("last_verdict") or state.get("last_watchdog_verdict")
    return str(verdict or "").strip().upper()


def ci_conclusion(state: dict[str, Any]) -> str:
    return str(state.get("ci_status", {}).get("conclusion", "")).strip().lower()


def latest_eval_result(state: dict[str, Any]) -> str:
    result = state.get("last_eval_result")
    if isinstance(result, str) and result.strip() and result.upper() not in {"TBD", "NONE", "N/A"}:
        return result.strip().upper()

    refs = state.get("eval_results") or []
    if not isinstance(refs, list) or not refs:
        return ""
    latest_ref = str(refs[-1])
    path = ROOT / latest_ref
    if not path.exists():
        path = ROOT / "evals" / "results" / Path(latest_ref).name
    if not path.exists():
        return ""
    try:
        latest = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ""
    return str(latest.get("verdict", "")).strip().upper()


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


def gh_pr_view(pr: str) -> tuple[dict[str, Any], str]:
    if not shutil.which("gh"):
        return {}, "GitHub CLI `gh` is not installed."
    command = [
        "gh",
        "pr",
        "view",
        "--json",
        "number,url,state,isDraft,mergeable,mergeStateStatus,reviewDecision,headRefName,baseRefName",
    ]
    if pr:
        command.append(pr)
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        return {}, result.stdout.strip()
    try:
        return json.loads(result.stdout), ""
    except json.JSONDecodeError as exc:
        return {}, f"PR metadata was not JSON: {exc}"


def load_pr(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if args.pr_from_file:
        try:
            return json.loads(Path(args.pr_from_file).read_text()), ""
        except json.JSONDecodeError as exc:
            return {}, f"PR metadata file was not JSON: {exc}"
    if args.mode in {"pr", "merge", "release"}:
        return gh_pr_view(args.pr)
    return {}, ""


def add_issue(issues: list[str], issue: str) -> None:
    if issue and issue not in issues:
        issues.append(issue)


def evaluate(args: argparse.Namespace, state: dict[str, Any], pr: dict[str, Any], pr_error: str) -> tuple[str, list[str], list[str]]:
    blockers = open_blockers(state)
    blocking: list[str] = []
    warnings: list[str] = []

    if blockers:
        add_issue(blocking, f"{len(blockers)} open blocker(s) remain.")

    watchdog = latest_watchdog(state)
    if args.require_watchdog_pass and watchdog != "PASS":
        add_issue(blocking, f"Watchdog verdict is not PASS: {watchdog or 'missing'}.")

    if args.require_ci_pass and ci_conclusion(state) not in PASS_CI:
        add_issue(blocking, f"CI is not passing: {ci_conclusion(state) or 'missing'}.")

    if args.require_latest_eval_pass and latest_eval_result(state) != "PASS":
        add_issue(blocking, f"Latest eval result is not PASS: {latest_eval_result(state) or 'missing'}.")

    if args.require_human_approval and not approval_exists(state):
        add_issue(blocking, "Required human approval artifact is missing.")

    guard_violations = file_guard_violations(state)
    if args.strict_file_guard and guard_violations:
        add_issue(blocking, f"{len(guard_violations)} historical file guard violation(s) found.")
    elif guard_violations:
        add_issue(warnings, f"{len(guard_violations)} historical file guard violation(s) recorded; ensure blockers are resolved.")

    if pr_error:
        if args.mode in {"merge", "release"}:
            add_issue(blocking, f"Unable to read PR metadata: {pr_error}")
        else:
            add_issue(warnings, f"Unable to read PR metadata: {pr_error}")

    if pr:
        state_value = str(pr.get("state", "")).upper()
        review = str(pr.get("reviewDecision", "")).upper()
        merge_state = str(pr.get("mergeStateStatus", "")).upper()
        mergeable = str(pr.get("mergeable", "")).upper()
        if state_value and state_value != "OPEN":
            add_issue(blocking, f"PR is not open: {state_value}.")
        if pr.get("isDraft") and not args.allow_draft_pr:
            add_issue(blocking, "PR is draft.")
        if args.mode in {"merge", "release"} and review not in {"APPROVED"} and not args.allow_review_pending:
            add_issue(blocking, f"PR review is not approved: {review or 'missing'}.")
        if args.mode in {"merge", "release"} and merge_state not in {"CLEAN", "HAS_HOOKS", "UNKNOWN"}:
            add_issue(blocking, f"PR merge state is not clean: {merge_state or 'missing'}.")
        if args.mode in {"merge", "release"} and mergeable in {"CONFLICTING", "FALSE"}:
            add_issue(blocking, f"PR is not mergeable: {mergeable}.")

    if blocking:
        if any("CI is not passing" in item or "PR is draft" in item or "review is not approved" in item for item in blocking):
            return "WAITING", blocking, warnings
        return "STOP", blocking, warnings
    return "PASS", blocking, warnings


def write_report(args: argparse.Namespace, state: dict[str, Any], pr: dict[str, Any], decision: str, blocking: list[str], warnings: list[str]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "id": f"{compact_ts()}-release-gate",
        "role": "release-gate",
        "mode": args.mode,
        "status": "completed",
        "verdict": decision,
        "summary": f"Release gate decision: {decision}",
        "blocking": blocking,
        "warnings": warnings,
        "created_at": now(),
        "policy": state.get("operating_policy", {}),
        "pr": pr,
        "evidence": {
            "watchdog": latest_watchdog(state),
            "latest_eval_result": latest_eval_result(state),
            "last_eval_result_artifact": state.get("last_eval_result_artifact", ""),
            "ci_status": state.get("ci_status", {}),
            "open_blockers_count": len(open_blockers(state)),
            "human_approval": approval_exists(state),
            "file_guard_violations_count": len(file_guard_violations(state)),
        },
    }
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return path


def maybe_open_blocker(state: dict[str, Any], decision: str, blocking: list[str], report_path: Path) -> None:
    if decision == "PASS" or not blocking:
        return
    state.setdefault("open_blockers", []).append(
        {
            "id": f"blocker-{compact_ts()}",
            "status": "open",
            "severity": "high" if decision == "STOP" else "medium",
            "owner": "release-gate",
            "description": f"Release gate {decision}: {blocking[0]}",
            "created_at": now(),
            "evidence": str(report_path.relative_to(ROOT)),
        }
    )


def main() -> int:
    args = parse_args()
    policy = load_policy(args)
    apply_policy(args, policy)
    state = load_state()
    state.setdefault("operating_policy", {})["path"] = str(Path(args.policy))
    if policy.get("profile"):
        state.setdefault("operating_policy", {})["profile"] = policy.get("profile")
    state.setdefault("operating_policy", {})["last_loaded_at"] = now() if policy else state.setdefault("operating_policy", {}).get("last_loaded_at", "TBD")
    pr, pr_error = load_pr(args)
    decision, blocking, warnings = evaluate(args, state, pr, pr_error)
    report_path = write_report(args, state, pr, decision, blocking, warnings)

    state.setdefault("structured_reports", []).append(str(report_path.relative_to(ROOT)))
    state["release_gate"] = {
        "last_decision": decision,
        "last_checked_at": now(),
        "last_report": str(report_path.relative_to(ROOT)),
        "mode": args.mode,
        "blocking": blocking,
        "warnings": warnings,
    }
    if args.open_blocker:
        maybe_open_blocker(state, decision, blocking, report_path)
    save_state(state)
    log_event("Release Gate", decision, str(report_path.relative_to(ROOT)))
    print(json.dumps(state["release_gate"], indent=2, sort_keys=True))
    return 0 if decision == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
