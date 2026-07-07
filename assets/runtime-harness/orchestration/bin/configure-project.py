#!/usr/bin/env python3
"""Configure project-specific orchestration state after harness installation."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"
POLICY_FILE = ROOT / "operating-policy.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def load_policy() -> dict[str, Any]:
    if not POLICY_FILE.exists():
        return {
            "version": 1,
            "profile": "standard",
            "gates": {},
            "run_cycle": {},
        }
    try:
        policy = json.loads(POLICY_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid operating policy JSON: {exc}") from exc
    if not isinstance(policy, dict):
        raise SystemExit("operating-policy.json must contain an object.")
    policy.setdefault("version", 1)
    policy.setdefault("profile", "standard")
    policy.setdefault("gates", {})
    policy.setdefault("run_cycle", {})
    return policy


def save_policy(policy: dict[str, Any]) -> None:
    POLICY_FILE.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n")


def log_event(event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": "configure-project", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def split_csv(values: list[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        for part in value.split(","):
            text = part.strip()
            if text:
                items.append(text)
    return items


def apply_list(state: dict[str, Any], key: str, values: list[str], append: bool) -> None:
    items = split_csv(values)
    if not items:
        return
    if append:
        existing = state.get(key)
        merged = existing if isinstance(existing, list) else []
        for item in items:
            if item not in merged:
                merged.append(item)
        state[key] = merged
    else:
        state[key] = items


def apply_scalar(state: dict[str, Any], key: str, value: str | None) -> None:
    if value is not None:
        state[key] = value


def parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "yes", "1", "required"}:
        return True
    if normalized in {"false", "no", "0", "not-required"}:
        return False
    raise SystemExit(f"Expected boolean value, got: {value}")


def update_nested_defaults(state: dict[str, Any]) -> None:
    current_phase = state.get("current_phase", "TBD")
    state.setdefault("write_lock", {})
    state["write_lock"].setdefault("status", "inactive")
    state["write_lock"].setdefault("owner", "Builder")
    state["write_lock"]["scope"] = state["write_lock"].get("scope") or current_phase
    state["write_lock"]["allowed_files"] = state.get(
        "allowed_files", state["write_lock"].get("allowed_files", [])
    )
    state["write_lock"]["forbidden_files"] = state.get(
        "forbidden_files", state["write_lock"].get("forbidden_files", [])
    )

    state.setdefault("phase_gate", {})
    state["phase_gate"]["authorized_phase"] = (
        state["phase_gate"].get("authorized_phase") or current_phase
    )
    state["phase_gate"].setdefault("unauthorized_phases", [])
    state["phase_gate"].setdefault(
        "next_phase_requires",
        [
            "QA pass",
            "Security pass when applicable",
            "Eval pass",
            "Architect decision",
            "Human approval for high-impact behavior",
        ],
    )

    state.setdefault("blocking_policy", {})
    state["blocking_policy"].setdefault("mode", "stop-and-ask")
    state["blocking_policy"].setdefault("recovery_limit", 1)
    state["blocking_policy"].setdefault("low_risk_recovery_allowed", True)
    state.setdefault("connected_tests", [])
    test_command = state.get("test_command")
    if (
        isinstance(test_command, str)
        and test_command.strip()
        and test_command.upper() not in {"TBD", "NONE", "N/A"}
    ):
        if test_command not in state["connected_tests"]:
            state["connected_tests"].append(test_command)
    state.setdefault("quality_rubrics", ["evals/rubrics/project-quality-rubric.md"])
    state.setdefault("pr_diff_reports", [])
    state.setdefault(
        "watchdog_evidence",
        {
            "last_verdict": "TBD",
            "last_prepared_at": "TBD",
            "last_report": "TBD",
            "missing_evidence": [],
            "connected_tests": state.get("connected_tests", []),
            "eval_fixtures": state.get("eval_fixtures", []),
            "eval_results": state.get("eval_results", []),
            "pr_diff_report": "TBD",
            "quality_rubric": "evals/rubrics/project-quality-rubric.md",
        },
    )
    state.setdefault(
        "decision_policy",
        {
            "profile": "risk-bucketed",
            "low_risk": {
                "default_action": "System may decide and act autonomously after recording evidence."
            },
            "medium_risk": {
                "default_action": "Research first, then escalate if uncertainty or product impact remains.",
                "confidence_threshold": 0.8,
            },
            "high_risk": {"default_action": "Human Product Owner approval required before action."},
            "last_decision": "TBD",
            "last_report": "TBD",
        },
    )
    state.setdefault("state_doc", {})["path"] = state.get(
        "state_file_path", "docs/project-roadmap-state.md"
    )
    state.setdefault("operating_policy", {})
    state["operating_policy"].setdefault("path", "operating-policy.json")
    state["operating_policy"].setdefault("profile", "standard")


def maybe_run_sync_state_doc(args: argparse.Namespace) -> None:
    if not args.sync_state_doc:
        return
    command = ["python3", str(ROOT / "bin" / "sync-state-doc.py"), "--write-report"]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        raise SystemExit(f"sync-state-doc.py failed:\n{result.stdout}")


def configure(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state()
    policy = load_policy()
    apply_scalar(state, "project_name", args.project_name)
    apply_scalar(state, "repo", args.repo_name)
    apply_scalar(state, "roadmap", args.roadmap_name)
    apply_scalar(state, "current_phase", args.current_phase)
    apply_scalar(state, "current_objective", args.current_objective)
    apply_scalar(state, "state_file_path", args.state_file_path)
    apply_scalar(state, "active_branch", args.active_branch)
    apply_scalar(state, "active_pr", args.active_pr)
    apply_scalar(state, "test_command", args.test_command)

    human_required = parse_bool(args.human_approval_required)
    if human_required is not None:
        state["human_approval_required"] = human_required

    apply_list(state, "allowed_files", args.allowed_file, args.append)
    apply_list(state, "forbidden_files", args.forbidden_file, args.append)
    apply_list(state, "preserved_components", args.preserved_component, args.append)
    apply_list(state, "forbidden_changes", args.forbidden_change, args.append)
    apply_list(state, "high_risk_areas", args.high_risk_area, args.append)
    apply_list(state, "controlled_taxonomy", args.controlled_taxonomy, args.append)
    apply_list(state, "eval_fixtures", args.eval_fixture, args.append)
    apply_list(state, "known_risks", args.known_risk, args.append)

    if args.blocker_mode:
        state.setdefault("blocking_policy", {})["mode"] = args.blocker_mode
    if args.blocker_recovery_limit is not None:
        state.setdefault("blocking_policy", {})["recovery_limit"] = args.blocker_recovery_limit
    if args.policy_profile:
        policy["profile"] = args.policy_profile
        state.setdefault("operating_policy", {})["profile"] = args.policy_profile
    policy_bool_args = {
        "require_watchdog_pass": args.policy_require_watchdog_pass,
        "require_latest_eval_pass": args.policy_require_latest_eval_pass,
        "require_ci_pass": args.policy_require_ci_pass,
        "require_human_approval": args.policy_require_human_approval,
        "strict_file_guard": args.policy_strict_file_guard,
    }
    for key, value in policy_bool_args.items():
        parsed = parse_bool(value)
        if parsed is not None:
            policy.setdefault("gates", {})[key] = parsed
    cycle_bool_args = {
        "release_gate": args.policy_release_gate,
        "strict_gates": args.policy_strict_gates,
        "watch_ci": args.policy_watch_ci,
        "ci_required": args.policy_ci_required,
        "remediate_on_gate_failure": args.policy_remediate_on_gate_failure,
    }
    for key, value in cycle_bool_args.items():
        parsed = parse_bool(value)
        if parsed is not None:
            policy.setdefault("run_cycle", {})[key] = parsed
    if args.policy_release_mode:
        policy.setdefault("run_cycle", {})["release_mode"] = args.policy_release_mode
    if args.authorized_phase:
        state.setdefault("phase_gate", {})["authorized_phase"] = args.authorized_phase
    if args.unauthorized_phase:
        state.setdefault("phase_gate", {})
        values = split_csv(args.unauthorized_phase)
        if args.append:
            existing = state["phase_gate"].get("unauthorized_phases", [])
            if not isinstance(existing, list):
                existing = []
            for item in values:
                if item not in existing:
                    existing.append(item)
            state["phase_gate"]["unauthorized_phases"] = existing
        else:
            state["phase_gate"]["unauthorized_phases"] = values

    update_nested_defaults(state)
    state.setdefault("operating_policy", {})["path"] = "operating-policy.json"
    state["operating_policy"]["profile"] = policy.get("profile", "standard")
    save_policy(policy)
    save_state(state)
    log_event("configured", state.get("project_name", "TBD"))
    maybe_run_sync_state_doc(args)
    return load_state()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name")
    parser.add_argument("--repo-name")
    parser.add_argument("--roadmap-name")
    parser.add_argument("--current-phase")
    parser.add_argument("--current-objective")
    parser.add_argument("--state-file-path")
    parser.add_argument("--active-branch")
    parser.add_argument("--active-pr")
    parser.add_argument("--test-command")
    parser.add_argument(
        "--human-approval-required",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
    parser.add_argument("--allowed-file", action="append", default=[])
    parser.add_argument("--forbidden-file", action="append", default=[])
    parser.add_argument("--preserved-component", action="append", default=[])
    parser.add_argument("--forbidden-change", action="append", default=[])
    parser.add_argument("--high-risk-area", action="append", default=[])
    parser.add_argument("--controlled-taxonomy", action="append", default=[])
    parser.add_argument("--eval-fixture", action="append", default=[])
    parser.add_argument("--known-risk", action="append", default=[])
    parser.add_argument("--authorized-phase")
    parser.add_argument("--unauthorized-phase", action="append", default=[])
    parser.add_argument(
        "--blocker-mode",
        choices=[
            "stop-and-ask",
            "bounded-recovery",
            "docs-only-continue",
            "draft-pr-with-blockers",
            "backlog-and-pause",
        ],
    )
    parser.add_argument("--blocker-recovery-limit", type=int)
    parser.add_argument("--policy-profile")
    parser.add_argument(
        "--policy-require-watchdog-pass",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
    parser.add_argument(
        "--policy-require-latest-eval-pass",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
    parser.add_argument(
        "--policy-require-ci-pass",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
    parser.add_argument(
        "--policy-require-human-approval",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
    parser.add_argument(
        "--policy-strict-file-guard",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
    parser.add_argument(
        "--policy-release-gate",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
    parser.add_argument(
        "--policy-strict-gates",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
    parser.add_argument(
        "--policy-watch-ci",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
    parser.add_argument(
        "--policy-ci-required",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
    parser.add_argument(
        "--policy-remediate-on-gate-failure",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
    parser.add_argument("--policy-release-mode", choices=["status", "pr", "merge", "release"])
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append list values instead of replacing the target lists.",
    )
    parser.add_argument(
        "--sync-state-doc",
        action="store_true",
        help="Refresh the shared markdown state file after configuration.",
    )
    parser.add_argument("--json", action="store_true", help="Print updated state as JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = configure(args)
    if args.json:
        print(json.dumps(state, indent=2, sort_keys=True))
    else:
        print("Project orchestration state configured.")
        print(f"Project: {state.get('project_name', 'TBD')}")
        print(f"Phase: {state.get('current_phase', 'TBD')}")
        print(f"State file path: {state.get('state_file_path', 'TBD')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
