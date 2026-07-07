#!/usr/bin/env python3
"""Run a guarded multi-agent orchestration cycle.

Dry-run by default: prepares prompts and captures runner output. Git writes,
pushes, and PR creation require explicit flags.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROLE_SCRIPTS = {
    "builder": "run-builder.sh",
    "qa": "run-qa.sh",
    "security": "run-security.sh",
    "eval-builder": "run-eval-builder.sh",
    "eval": "run-eval.sh",
    "watchdog": "run-watchdog.sh",
    "remediation": "run-remediation.sh",
    "architect": "run-architect.sh",
    "docs": "run-docs.sh",
}

DEFAULT_ROLES = [
    "builder",
    "qa",
    "security",
    "eval-builder",
    "eval",
    "watchdog",
    "architect",
    "docs",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an orchestration cycle safely.")
    parser.add_argument(
        "--roles",
        default=",".join(DEFAULT_ROLES),
        help="Comma-separated role list. Defaults to the full cycle.",
    )
    parser.add_argument(
        "--agent-command",
        default=os.environ.get("AGENT_COMMAND", ""),
        help="Command that receives each role prompt on stdin. Omit to prepare prompts only.",
    )
    parser.add_argument(
        "--create-branch",
        default="",
        help="Create/switch to a new branch before running roles. Requires --allow-git-write.",
    )
    parser.add_argument(
        "--commit-message",
        default="",
        help="Commit current changes after roles complete. Requires --allow-git-write.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push the current branch. Requires --allow-git-write.",
    )
    parser.add_argument(
        "--create-pr",
        action="store_true",
        help="Create a draft GitHub PR with report summary. Requires --allow-git-write and --push.",
    )
    parser.add_argument(
        "--pr-title",
        default="",
        help="Draft PR title. Defaults to current branch name.",
    )
    parser.add_argument(
        "--base",
        default="",
        help="Base branch for PR creation. Let gh infer it when omitted.",
    )
    parser.add_argument(
        "--allow-git-write",
        action="store_true",
        help="Permit branch creation, commits, pushes, and PR creation.",
    )
    parser.add_argument(
        "--allow-dirty-branch-create",
        action="store_true",
        help="Allow branch creation while the worktree is dirty.",
    )
    parser.add_argument(
        "--skip-watchdog-pr-check",
        action="store_true",
        help="Allow PR creation without a PASS watchdog report.",
    )
    parser.add_argument(
        "--strict-gates",
        action="store_true",
        help="Block commit, push, and PR creation unless open_blockers is empty and Watchdog verdict is PASS.",
    )
    parser.add_argument(
        "--remediate-on-gate-failure",
        action="store_true",
        help="Prepare a remediation prompt/report when strict or PR gates fail.",
    )
    parser.add_argument(
        "--require-ci-pass",
        action="store_true",
        help="Block strict-gated actions unless state.json ci_status.conclusion is success/passed/green.",
    )
    parser.add_argument(
        "--require-latest-eval-pass",
        action="store_true",
        help="Block strict-gated actions unless the latest Eval Monitor result is PASS.",
    )
    parser.add_argument(
        "--policy",
        default="operating-policy.json",
        help="Operating policy JSON path, relative to orchestration root unless absolute.",
    )
    parser.add_argument(
        "--no-policy",
        action="store_true",
        help="Ignore operating-policy.json defaults for this run.",
    )
    parser.add_argument(
        "--watch-ci",
        action="store_true",
        help="Refresh PR check status with watch-ci.py before CI-gated actions.",
    )
    parser.add_argument(
        "--ci-pr",
        default="",
        help="PR number, URL, or branch for --watch-ci. Defaults to current branch PR.",
    )
    parser.add_argument(
        "--ci-required",
        action="store_true",
        help="Only inspect required PR checks when --watch-ci is enabled.",
    )
    parser.add_argument(
        "--ci-timeout-seconds",
        type=float,
        default=0.0,
        help="When positive, wait up to this many seconds for CI to finish.",
    )
    parser.add_argument(
        "--ci-from-file",
        default="",
        help="Read PR check JSON from a file when --watch-ci is enabled.",
    )
    parser.add_argument(
        "--require-human-approval",
        action="store_true",
        help="Block PR creation unless an approved human approval artifact exists.",
    )
    parser.add_argument(
        "--no-normalize-reports",
        action="store_true",
        help="Skip automatic markdown-to-JSON report normalization.",
    )
    parser.add_argument(
        "--open-blockers-from-reports",
        action="store_true",
        help="Open blockers for explicit negative verdicts or blocker lists in role reports.",
    )
    parser.add_argument(
        "--dispatch-subagents",
        action="store_true",
        help="Run read-only specialist subagents for each selected role after role reports are normalized.",
    )
    parser.add_argument(
        "--subagent-command",
        default=os.environ.get("SUBAGENT_COMMAND", ""),
        help="Command that receives each subagent prompt on stdin. Defaults to SUBAGENT_COMMAND.",
    )
    parser.add_argument(
        "--subagent-open-blockers",
        action="store_true",
        help="Open blockers for explicit negative subagent verdicts or blocker lists.",
    )
    parser.add_argument(
        "--subagent-fail-on-negative",
        action="store_true",
        help="Stop the cycle when any subagent reports a negative verdict.",
    )
    parser.add_argument(
        "--disable-file-guard",
        action="store_true",
        help="Disable role file-change guard checks. Use only when debugging the harness.",
    )
    parser.add_argument(
        "--no-file-guard-blocker",
        action="store_true",
        help="Do not open blockers when file guard violations are found.",
    )
    parser.add_argument(
        "--release-gate",
        action="store_true",
        help="Run release-gate.py before git write/PR actions.",
    )
    parser.add_argument(
        "--release-mode",
        choices=["status", "pr", "merge", "release"],
        default="status",
        help="Release gate mode.",
    )
    parser.add_argument(
        "--release-pr",
        default="",
        help="PR number, URL, or branch for release-gate.py.",
    )
    parser.add_argument(
        "--release-pr-from-file",
        default="",
        help="Read release-gate PR metadata JSON from a file.",
    )
    parser.add_argument(
        "--release-open-blocker",
        action="store_true",
        help="Open a blocker when release-gate.py does not PASS.",
    )
    parser.add_argument(
        "--release-strict-file-guard",
        action="store_true",
        help="Fail release gate on any recorded file guard violation, even if blockers were resolved.",
    )
    parser.add_argument(
        "--allow-draft-pr",
        action="store_true",
        help="Allow draft PRs in release-gate.py.",
    )
    parser.add_argument(
        "--allow-review-pending",
        action="store_true",
        help="Allow pending/missing PR review in release-gate.py.",
    )
    parser.add_argument(
        "--sync-state-doc",
        action="store_true",
        help="Refresh the human-readable shared project state markdown after the cycle.",
    )
    return parser.parse_args()


def run(
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def require_git_write(args: argparse.Namespace, action: str) -> None:
    if not args.allow_git_write:
        raise SystemExit(f"{action} requires --allow-git-write.")


def git_root(start: Path) -> Path:
    result = run(["git", "rev-parse", "--show-toplevel"], start, check=False)
    if result.returncode != 0:
        raise SystemExit("This adapter must be run inside a git repository.")
    return Path(result.stdout.strip()).resolve()


def short_status(repo: Path) -> str:
    return run(["git", "status", "--short"], repo).stdout.strip()


def current_branch(repo: Path) -> str:
    return run(["git", "branch", "--show-current"], repo).stdout.strip()


def append_event(root: Path, role: str, event: str, note: str) -> None:
    event_log = root / "events.log"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "role": role,
        "event": event,
        "note": note,
    }
    with event_log.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def role_report_name(role: str) -> str:
    safe_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{safe_ts}-{role}.md"


def guard_snapshot(root: Path, bin_dir: Path, role: str, enabled: bool) -> Path | None:
    if not enabled:
        return None
    result = run(
        ["python3", str(bin_dir / "guard-files.py"), "snapshot", "--role", role],
        root,
        check=False,
    )
    print(result.stdout, end="")
    append_event(root, "File Guard", "snapshot_requested", f"role={role} exit={result.returncode}")
    if result.returncode != 0:
        raise SystemExit(f"File guard snapshot failed for {role}:\n{result.stdout}")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return Path(lines[-1]) if lines else None


def guard_check(
    root: Path,
    bin_dir: Path,
    role: str,
    snapshot: Path | None,
    enabled: bool,
    open_blocker: bool,
) -> None:
    if not enabled or snapshot is None:
        return
    command = [
        "python3",
        str(bin_dir / "guard-files.py"),
        "check",
        "--snapshot",
        str(snapshot),
        "--role",
        role,
    ]
    if open_blocker:
        command.append("--open-blocker")
    result = run(command, root, check=False)
    print(result.stdout, end="")
    append_event(root, "File Guard", "check_completed", f"role={role} exit={result.returncode}")
    if result.returncode != 0:
        raise SystemExit(f"File guard blocked {role}. See state.json open_blockers and file_guard_checks.")


def run_roles(
    root: Path,
    bin_dir: Path,
    roles: list[str],
    agent_command: str,
    guard_enabled: bool = True,
    guard_open_blocker: bool = True,
) -> list[Path]:
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    reports: list[Path] = []

    for role in roles:
        script = ROLE_SCRIPTS.get(role)
        if script is None:
            raise SystemExit(f"Unknown role: {role}")
        env = os.environ.copy()
        if agent_command:
            env["AGENT_COMMAND"] = agent_command
        snapshot = guard_snapshot(root, bin_dir, role, guard_enabled)
        result = run(["bash", str(bin_dir / script)], root, env=env, check=False)
        report_path = reports_dir / role_report_name(role)
        report_path.write_text(
            f"# {role} report\n\n"
            f"Exit code: {result.returncode}\n\n"
            "```text\n"
            f"{result.stdout}"
            "\n```\n"
        )
        reports.append(report_path)
        append_event(root, role, "runner_completed", f"{report_path.name} exit={result.returncode}")
        guard_check(root, bin_dir, role, snapshot, guard_enabled, guard_open_blocker)
        if result.returncode != 0:
            raise SystemExit(f"Role {role} failed. See {report_path}")

    return reports


def normalize_reports(
    root: Path,
    bin_dir: Path,
    reports: list[Path],
    open_blockers: bool,
    enabled: bool,
) -> list[Path]:
    if not enabled or not reports:
        return []
    command = ["python3", str(bin_dir / "normalize-report.py")]
    if open_blockers:
        command.append("--open-blockers")
    command.extend(str(report) for report in reports)
    result = run(command, root, check=False)
    print(result.stdout, end="")
    append_event(root, "Report Normalizer", "completed", f"exit={result.returncode}")
    if result.returncode != 0:
        raise SystemExit(f"Report normalization failed:\n{result.stdout}")
    return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def dispatch_subagents_if_requested(
    root: Path,
    bin_dir: Path,
    roles: list[str],
    args: argparse.Namespace,
) -> None:
    if not args.dispatch_subagents:
        return
    for role in roles:
        command = ["python3", str(bin_dir / "dispatch-subagents.py"), "--role", role]
        if args.subagent_command:
            command.extend(["--agent-command", args.subagent_command])
        if args.subagent_open_blockers or args.strict_gates:
            command.append("--open-blockers")
        if args.subagent_fail_on_negative:
            command.append("--fail-on-negative")
        if args.disable_file_guard:
            command.append("--disable-file-guard")
        if args.no_file_guard_blocker:
            command.append("--no-file-guard-blocker")
        result = run(command, root, check=False)
        print(result.stdout, end="")
        append_event(root, "Subagent Dispatcher", "completed", f"role={role} exit={result.returncode}")
        if result.returncode != 0:
            raise SystemExit(f"Subagent dispatch failed for {role}:\n{result.stdout}")


def latest_watchdog_report(root: Path) -> Path | None:
    reports = sorted((root / "reports").glob("*-watchdog.md"))
    return reports[-1] if reports else None


def load_state(root: Path) -> dict:
    state_file = root / "state.json"
    if not state_file.exists():
        raise SystemExit(f"Missing orchestration state file: {state_file}")
    try:
        return json.loads(state_file.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid orchestration state JSON: {exc}") from exc


def load_policy(root: Path, args: argparse.Namespace) -> dict:
    if args.no_policy:
        return {}
    path = Path(args.policy)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        return {}
    try:
        policy = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid operating policy JSON: {path}: {exc}") from exc
    if not isinstance(policy, dict):
        raise SystemExit(f"Operating policy must contain a JSON object: {path}")
    return policy


def apply_policy_defaults(root: Path, args: argparse.Namespace) -> None:
    policy = load_policy(root, args)
    if not policy:
        return
    gates = policy.get("gates") if isinstance(policy.get("gates"), dict) else {}
    cycle = policy.get("run_cycle") if isinstance(policy.get("run_cycle"), dict) else {}
    args.require_ci_pass = args.require_ci_pass or bool(gates.get("require_ci_pass"))
    args.require_latest_eval_pass = args.require_latest_eval_pass or bool(gates.get("require_latest_eval_pass"))
    args.require_human_approval = args.require_human_approval or bool(gates.get("require_human_approval"))
    args.release_strict_file_guard = args.release_strict_file_guard or bool(gates.get("strict_file_guard"))
    args.release_gate = args.release_gate or bool(cycle.get("release_gate"))
    args.strict_gates = args.strict_gates or bool(cycle.get("strict_gates"))
    args.watch_ci = args.watch_ci or bool(cycle.get("watch_ci"))
    args.ci_required = args.ci_required or bool(cycle.get("ci_required"))
    args.remediate_on_gate_failure = args.remediate_on_gate_failure or bool(cycle.get("remediate_on_gate_failure"))
    release_mode = cycle.get("release_mode")
    if args.release_mode == "status" and isinstance(release_mode, str) and release_mode in {"status", "pr", "merge", "release"}:
        args.release_mode = release_mode

    state = load_state(root)
    state.setdefault("operating_policy", {})["path"] = str(Path(args.policy))
    if policy.get("profile"):
        state.setdefault("operating_policy", {})["profile"] = policy.get("profile")
    state.setdefault("operating_policy", {})["last_loaded_at"] = datetime.now(timezone.utc).isoformat()
    (root / "state.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def open_blockers(root: Path) -> list[str]:
    raw_blockers = load_state(root).get("open_blockers", [])
    if raw_blockers is None:
        return []
    if isinstance(raw_blockers, list):
        blockers: list[str] = []
        for item in raw_blockers:
            if isinstance(item, dict):
                if item.get("status", "open") in {"resolved", "closed"}:
                    continue
                description = item.get("description") or item.get("id") or json.dumps(item, sort_keys=True)
                blockers.append(str(description))
            elif str(item).strip():
                blockers.append(str(item))
        return blockers
    if isinstance(raw_blockers, str):
        normalized = raw_blockers.strip()
        if not normalized or normalized.upper() in {"TBD", "NONE", "N/A", "NA", "[]"}:
            return []
        return [normalized]
    if isinstance(raw_blockers, dict):
        return [
            f"{key}: {value}"
            for key, value in raw_blockers.items()
            if str(value).strip()
        ]
    return [str(raw_blockers)]


def latest_structured_report(root: Path, role: str) -> dict | None:
    reports_dir = root / "reports" / "json"
    candidates = sorted(reports_dir.glob(f"*-{role}.json"))
    if not candidates:
        return None
    try:
        return json.loads(candidates[-1].read_text())
    except json.JSONDecodeError:
        return None


def watchdog_verdict(root: Path) -> tuple[str | None, Path | None]:
    structured = latest_structured_report(root, "watchdog")
    if structured:
        verdict = structured.get("verdict") or structured.get("status")
        if verdict:
            return str(verdict).upper(), root / "reports" / "json" / f"{structured.get('id', 'watchdog')}.json"

    state_verdict = load_state(root).get("watchdog", {}).get("last_verdict")
    if isinstance(state_verdict, str) and state_verdict.strip() and state_verdict.upper() not in {"TBD", "NONE", "N/A"}:
        return state_verdict.upper(), root / "state.json"

    report = latest_watchdog_report(root)
    if report is None:
        return None, None
    text = report.read_text().upper()
    verdicts: list[str] = []
    for line in text.splitlines():
        match = re.match(
            r"^\s*(?:[-*]\s*)?(?:WATCHDOG\s+VERDICT|VERDICT)?\s*:?\s*"
            r"(PASS|REQUEST_FIXES|PROCESS_WARNING|STOP)\s*[.!]?\s*$",
            line,
        )
        if match:
            verdicts.append(match.group(1))
    return (verdicts[-1] if verdicts else None), report


def ci_passed(state: dict) -> bool:
    conclusion = str(state.get("ci_status", {}).get("conclusion", "")).strip().lower()
    return conclusion in {"success", "succeeded", "passed", "pass", "green"}


def latest_eval_passed(root: Path, state: dict) -> tuple[bool, str]:
    result = state.get("last_eval_result")
    if isinstance(result, str) and result.strip() and result.upper() not in {"TBD", "NONE", "N/A"}:
        verdict = result.strip().upper()
        return verdict == "PASS", verdict

    refs = state.get("eval_results") or []
    if not isinstance(refs, list) or not refs:
        return False, "missing"
    latest_ref = str(refs[-1])
    path = root / latest_ref
    if not path.exists():
        path = root / "evals" / "results" / Path(latest_ref).name
    if not path.exists():
        return False, "missing"
    try:
        latest = json.loads(path.read_text())
    except json.JSONDecodeError:
        return False, "invalid"
    verdict = str(latest.get("verdict", "")).strip().upper() or "missing"
    return verdict == "PASS", verdict


def human_approval_exists(root: Path, state: dict) -> bool:
    approval_refs = state.get("human_approvals") or []
    approvals_dir = root / "approvals"
    for ref in approval_refs:
        path = root / str(ref)
        if not path.exists():
            path = approvals_dir / Path(str(ref)).name
        if not path.exists():
            continue
        try:
            approval = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if approval.get("decision") == "approved":
            return True
    return False


def gate_failure_message(
    root: Path,
    include_watchdog: bool = True,
    require_ci: bool = False,
    require_eval: bool = False,
    require_human_approval: bool = False,
) -> str | None:
    state = load_state(root)
    blockers = open_blockers(root)
    if blockers:
        blocker_list = "\n".join(f"- {blocker}" for blocker in blockers)
        return f"orchestration state has open blockers:\n{blocker_list}"

    if require_ci and not ci_passed(state):
        ci_status = state.get("ci_status", {})
        return (
            "CI gate is not passing."
            f" conclusion={ci_status.get('conclusion', 'missing')}"
            f" details={ci_status.get('details', '')}"
        )

    if require_eval:
        eval_passed, eval_verdict = latest_eval_passed(root, state)
        if not eval_passed:
            return f"latest Eval Monitor result is not PASS. Found: {eval_verdict}."

    if require_human_approval and not human_approval_exists(root, state):
        return "required human approval artifact is missing."

    if not include_watchdog:
        return None

    verdict, report = watchdog_verdict(root)
    if verdict != "PASS":
        report_note = f" Latest Watchdog report: {report}" if report else " No Watchdog report found."
        return (
            "latest Watchdog verdict is not PASS."
            f" Found: {verdict or 'missing'}."
            f"{report_note}"
        )
    return None


def run_remediation(root: Path, bin_dir: Path, agent_command: str, reason: str) -> Path:
    reports = run_roles(root, bin_dir, ["remediation"], agent_command)
    normalize_reports(root, bin_dir, reports, open_blockers=False, enabled=True)
    report = reports[-1]
    append_event(root, "Remediation", "gate_failure_remediation_prepared", reason)
    return report


def stop_for_gate_failure(
    root: Path,
    bin_dir: Path,
    args: argparse.Namespace,
    action: str,
    reason: str,
) -> None:
    detail = f"{action} blocked because {reason}"
    if args.remediate_on_gate_failure:
        report = run_remediation(root, bin_dir, args.agent_command, detail)
        detail += f"\nRemediation report prepared: {report}"
    raise SystemExit(detail)


def refresh_ci_if_requested(root: Path, bin_dir: Path, args: argparse.Namespace) -> None:
    if not args.watch_ci:
        return

    command = ["python3", str(bin_dir / "watch-ci.py")]
    if args.ci_pr:
        command.extend(["--pr", args.ci_pr])
    if args.ci_required:
        command.append("--required")
    if args.ci_timeout_seconds > 0:
        command.extend(["--watch", "--timeout-seconds", str(args.ci_timeout_seconds)])
    if args.ci_from_file:
        command.extend(["--from-file", args.ci_from_file])

    result = run(command, root, check=False)
    print(result.stdout, end="")
    append_event(root, "CI Monitor", "refreshed_by_run_cycle", f"exit={result.returncode}")


def run_release_gate_if_requested(
    root: Path,
    bin_dir: Path,
    args: argparse.Namespace,
    action: str,
) -> None:
    if not args.release_gate:
        return
    command = [
        "python3",
        str(bin_dir / "release-gate.py"),
        "--mode",
        args.release_mode,
    ]
    if args.release_pr:
        command.extend(["--pr", args.release_pr])
    if args.release_pr_from_file:
        command.extend(["--pr-from-file", args.release_pr_from_file])
    if args.require_ci_pass:
        command.append("--require-ci-pass")
    if args.require_latest_eval_pass:
        command.append("--require-latest-eval-pass")
    if args.require_human_approval:
        command.append("--require-human-approval")
    if args.release_open_blocker:
        command.append("--open-blocker")
    if args.release_strict_file_guard:
        command.append("--strict-file-guard")
    if args.allow_draft_pr:
        command.append("--allow-draft-pr")
    if args.allow_review_pending:
        command.append("--allow-review-pending")
    result = run(command, root, check=False)
    print(result.stdout, end="")
    append_event(root, "Release Gate", "run_cycle_gate", f"action={action} exit={result.returncode}")
    if result.returncode != 0:
        stop_for_gate_failure(root, bin_dir, args, action, "release gate did not PASS")


def sync_state_doc_if_requested(root: Path, bin_dir: Path, args: argparse.Namespace) -> None:
    if not args.sync_state_doc:
        return
    result = run(
        ["python3", str(bin_dir / "sync-state-doc.py"), "--write-report"],
        root,
        check=False,
    )
    print(result.stdout, end="")
    append_event(root, "State Doc Sync", "run_cycle_sync", f"exit={result.returncode}")
    if result.returncode != 0:
        raise SystemExit(f"State doc sync failed:\n{result.stdout}")


def enforce_strict_gates(
    root: Path,
    bin_dir: Path,
    args: argparse.Namespace,
    action: str,
) -> None:
    if not args.strict_gates:
        return
    reason = gate_failure_message(
        root,
        include_watchdog=True,
        require_ci=args.require_ci_pass,
        require_eval=args.require_latest_eval_pass,
    )
    if reason:
        stop_for_gate_failure(root, bin_dir, args, action, reason)


def validate_pr_creation_gates(
    root: Path,
    bin_dir: Path,
    args: argparse.Namespace,
) -> None:
    reason = gate_failure_message(
        root,
        include_watchdog=not args.skip_watchdog_pr_check,
        require_ci=args.require_ci_pass,
        require_eval=args.require_latest_eval_pass,
        require_human_approval=args.require_human_approval,
    )
    if reason:
        help_text = ""
        if "Watchdog" in reason:
            help_text = " Use --skip-watchdog-pr-check only with human approval."
        stop_for_gate_failure(root, bin_dir, args, "PR creation", reason + help_text)


def create_branch(repo: Path, args: argparse.Namespace) -> None:
    if not args.create_branch:
        return
    require_git_write(args, "Branch creation")
    if short_status(repo) and not args.allow_dirty_branch_create:
        raise SystemExit(
            "Worktree is dirty. Commit/stash first or pass --allow-dirty-branch-create."
        )
    run(["git", "switch", "-c", args.create_branch], repo)


def commit_changes(repo: Path, args: argparse.Namespace) -> None:
    if not args.commit_message:
        return
    require_git_write(args, "Commit")
    if not short_status(repo):
        print("No changes to commit.")
        return
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-m", args.commit_message], repo)


def push_branch(repo: Path, args: argparse.Namespace) -> None:
    if not args.push:
        return
    require_git_write(args, "Push")
    branch = current_branch(repo)
    if not branch:
        raise SystemExit("Cannot push from detached HEAD.")
    run(["git", "push", "-u", "origin", branch], repo)


def create_pr(repo: Path, root: Path, args: argparse.Namespace) -> None:
    if not args.create_pr:
        return
    require_git_write(args, "PR creation")
    if not args.push:
        raise SystemExit("--create-pr requires --push.")
    if not shutil.which("gh"):
        raise SystemExit("GitHub CLI `gh` is required for --create-pr.")

    branch = current_branch(repo)
    title = args.pr_title or branch
    body = [
        "## Orchestration Summary",
        "",
        f"- Branch: `{branch}`",
        f"- Watchdog report: `{latest_watchdog_report(root)}`",
        "- This PR was prepared by the orchestration adapter.",
        "",
        "Human approval is still required for high-impact behavior.",
    ]
    command = ["gh", "pr", "create", "--draft", "--title", title, "--body", "\n".join(body)]
    if args.base:
        command.extend(["--base", args.base])
    run(command, repo)


def main() -> int:
    args = parse_args()
    bin_dir = Path(__file__).resolve().parent
    root = bin_dir.parent
    apply_policy_defaults(root, args)
    repo = git_root(root)
    roles = [role.strip() for role in args.roles.split(",") if role.strip()]

    create_branch(repo, args)
    reports = run_roles(
        root,
        bin_dir,
        roles,
        args.agent_command,
        guard_enabled=not args.disable_file_guard,
        guard_open_blocker=not args.no_file_guard_blocker,
    )
    normalize_reports(
        root,
        bin_dir,
        reports,
        open_blockers=args.open_blockers_from_reports or args.strict_gates,
        enabled=not args.no_normalize_reports,
    )
    dispatch_subagents_if_requested(root, bin_dir, roles, args)
    refresh_ci_if_requested(root, bin_dir, args)
    sync_state_doc_if_requested(root, bin_dir, args)
    if args.commit_message:
        run_release_gate_if_requested(root, bin_dir, args, "Commit")
        enforce_strict_gates(root, bin_dir, args, "Commit")
    commit_changes(repo, args)
    if args.push:
        run_release_gate_if_requested(root, bin_dir, args, "Push")
        enforce_strict_gates(root, bin_dir, args, "Push")
    if args.create_pr:
        run_release_gate_if_requested(root, bin_dir, args, "PR creation")
        validate_pr_creation_gates(root, bin_dir, args)
        enforce_strict_gates(root, bin_dir, args, "PR creation")
    push_branch(repo, args)
    create_pr(repo, root, args)

    print("Orchestration cycle complete.")
    for report in reports:
        print(f"- {report.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
