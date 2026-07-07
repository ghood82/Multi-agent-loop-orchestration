#!/usr/bin/env python3
"""Collect first-time orchestration setup inputs and optionally apply them."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"

BLOCKER_MODES = [
    "stop-and-ask",
    "bounded-recovery",
    "docs-only-continue",
    "draft-pr-with-blockers",
    "backlog-and-pause",
]

AGENT_PROVIDERS = [
    "auto",
    "prompt-only",
    "codex-cli",
    "claude-code",
    "custom-command",
]

DECISION_POLICY_PROFILES = [
    "risk-bucketed",
    "human-heavy",
    "autonomous-low-risk-only",
]

PROFILE_DEFAULTS = {
    "standard": {
        "policy_require_watchdog_pass": "true",
        "policy_require_latest_eval_pass": "false",
        "policy_require_ci_pass": "false",
        "policy_require_human_approval": "false",
        "policy_strict_file_guard": "false",
        "policy_release_gate": "false",
        "policy_strict_gates": "false",
        "policy_watch_ci": "false",
        "policy_ci_required": "false",
        "policy_remediate_on_gate_failure": "false",
        "policy_release_mode": "status",
    },
    "strict-pr": {
        "policy_require_watchdog_pass": "true",
        "policy_require_latest_eval_pass": "true",
        "policy_require_ci_pass": "true",
        "policy_require_human_approval": "true",
        "policy_strict_file_guard": "true",
        "policy_release_gate": "true",
        "policy_strict_gates": "true",
        "policy_watch_ci": "true",
        "policy_ci_required": "true",
        "policy_remediate_on_gate_failure": "true",
        "policy_release_mode": "pr",
    },
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    try:
        state = json.loads(STATE_FILE.read_text())
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON: {exc}") from exc
    if not isinstance(state, dict):
        return {}
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": "setup-intake", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def prompt_value(label: str, default: str = "", *, non_interactive: bool) -> str:
    if non_interactive:
        return default
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def prompt_bool(label: str, default: bool, *, non_interactive: bool) -> bool:
    if non_interactive:
        return default
    suffix = "Y/n" if default else "y/N"
    value = input(f"{label} [{suffix}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "true", "1", "required"}


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def collect(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state()
    repo_default = state.get("repo") or ROOT.parent.name
    profile_default = args.policy_profile or state.get("operating_policy", {}).get(
        "profile", "standard"
    )
    if profile_default not in PROFILE_DEFAULTS:
        profile_default = "standard"

    data: dict[str, Any] = {
        "project_name": args.project_name
        or prompt_value(
            "Project name", state.get("project_name", "TBD"), non_interactive=args.non_interactive
        ),
        "repo_name": args.repo_name
        or prompt_value("Repo name", str(repo_default), non_interactive=args.non_interactive),
        "roadmap_name": args.roadmap_name
        or prompt_value(
            "Roadmap name", state.get("roadmap", "TBD"), non_interactive=args.non_interactive
        ),
        "current_phase": args.current_phase
        or prompt_value(
            "Current phase", state.get("current_phase", "TBD"), non_interactive=args.non_interactive
        ),
        "current_objective": args.current_objective
        or prompt_value(
            "Current objective",
            state.get("current_objective", "TBD"),
            non_interactive=args.non_interactive,
        ),
        "state_file_path": args.state_file_path
        or prompt_value(
            "Shared state file path",
            state.get("state_file_path", "docs/project-roadmap-state.md"),
            non_interactive=args.non_interactive,
        ),
        "test_command": args.test_command
        or prompt_value(
            "Primary test command",
            state.get("test_command", "TBD"),
            non_interactive=args.non_interactive,
        ),
        "active_branch": args.active_branch
        or prompt_value(
            "Active branch", state.get("active_branch", "TBD"), non_interactive=args.non_interactive
        ),
        "active_pr": args.active_pr
        or prompt_value(
            "Active PR", state.get("active_pr", "TBD"), non_interactive=args.non_interactive
        ),
        "blocker_mode": args.blocker_mode
        or prompt_value(
            "Blocker handling mode",
            state.get("blocking_policy", {}).get("mode", "stop-and-ask"),
            non_interactive=args.non_interactive,
        ),
        "blocker_recovery_limit": args.blocker_recovery_limit,
        "human_approval_required": args.human_approval_required,
        "policy_profile": profile_default,
        "agent_provider": args.agent_provider
        or prompt_value(
            "Agent provider",
            state.get("agent_adapter", {}).get("configured_provider", "auto"),
            non_interactive=args.non_interactive,
        ),
        "agent_command": args.agent_command
        or prompt_value("Agent command override", "", non_interactive=args.non_interactive),
        "decision_policy_profile": args.decision_policy_profile
        or prompt_value(
            "Decision policy profile",
            state.get("decision_policy", {}).get("profile", "risk-bucketed"),
            non_interactive=args.non_interactive,
        ),
    }

    if data["blocker_mode"] not in BLOCKER_MODES:
        raise SystemExit(
            f"Unsupported blocker mode: {data['blocker_mode']}. Choose one of: {', '.join(BLOCKER_MODES)}"
        )
    if data["agent_provider"] not in AGENT_PROVIDERS:
        raise SystemExit(
            f"Unsupported agent provider: {data['agent_provider']}. Choose one of: {', '.join(AGENT_PROVIDERS)}"
        )
    if data["decision_policy_profile"] not in DECISION_POLICY_PROFILES:
        raise SystemExit(
            f"Unsupported decision policy profile: {data['decision_policy_profile']}. Choose one of: {', '.join(DECISION_POLICY_PROFILES)}"
        )

    if data["blocker_recovery_limit"] is None:
        default_limit = str(state.get("blocking_policy", {}).get("recovery_limit", 1))
        limit = prompt_value(
            "Low-risk blocker recovery attempts",
            default_limit,
            non_interactive=args.non_interactive,
        )
        try:
            data["blocker_recovery_limit"] = int(limit)
        except ValueError as exc:
            raise SystemExit(f"Blocker recovery limit must be an integer: {limit}") from exc

    if data["human_approval_required"] is None:
        default_human = bool(state.get("human_approval_required", True))
        data["human_approval_required"] = (
            "true"
            if prompt_bool(
                "Require human approval for high-impact decisions",
                default_human,
                non_interactive=args.non_interactive,
            )
            else "false"
        )

    if not args.policy_profile:
        selected = prompt_value(
            "Operating policy profile", profile_default, non_interactive=args.non_interactive
        )
        if selected not in PROFILE_DEFAULTS:
            raise SystemExit(
                f"Unsupported policy profile: {selected}. Choose one of: {', '.join(PROFILE_DEFAULTS)}"
            )
        data["policy_profile"] = selected

    list_defaults = {
        "allowed_file": state.get("allowed_files", []),
        "forbidden_file": state.get("forbidden_files", []),
        "preserved_component": state.get("preserved_components", []),
        "forbidden_change": state.get("forbidden_changes", []),
        "high_risk_area": state.get("high_risk_areas", []),
        "controlled_taxonomy": state.get("controlled_taxonomy", []),
        "eval_fixture": state.get("eval_fixtures", []),
        "known_risk": state.get("known_risks", []),
    }
    for key, existing in list_defaults.items():
        supplied = getattr(args, key)
        if supplied:
            data[key] = supplied
            continue
        default = ", ".join(str(item) for item in existing) if isinstance(existing, list) else ""
        label = key.replace("_", " ").title()
        data[key] = split_csv(
            prompt_value(
                f"{label} (comma-separated)", default, non_interactive=args.non_interactive
            )
        )

    return data


def configure_command(data: dict[str, Any], *, sync_state_doc: bool) -> list[str]:
    command = [sys.executable, str(ROOT / "bin" / "configure-project.py")]
    scalar_flags = {
        "project_name": "--project-name",
        "repo_name": "--repo-name",
        "roadmap_name": "--roadmap-name",
        "current_phase": "--current-phase",
        "current_objective": "--current-objective",
        "state_file_path": "--state-file-path",
        "active_branch": "--active-branch",
        "active_pr": "--active-pr",
        "test_command": "--test-command",
        "human_approval_required": "--human-approval-required",
        "blocker_mode": "--blocker-mode",
        "policy_profile": "--policy-profile",
    }
    for key, flag in scalar_flags.items():
        value = data.get(key)
        if value and value != "TBD":
            command.extend([flag, str(value)])
    command.extend(["--blocker-recovery-limit", str(data["blocker_recovery_limit"])])

    profile_defaults = PROFILE_DEFAULTS[data["policy_profile"]]
    policy_flags = {
        "policy_require_watchdog_pass": "--policy-require-watchdog-pass",
        "policy_require_latest_eval_pass": "--policy-require-latest-eval-pass",
        "policy_require_ci_pass": "--policy-require-ci-pass",
        "policy_require_human_approval": "--policy-require-human-approval",
        "policy_strict_file_guard": "--policy-strict-file-guard",
        "policy_release_gate": "--policy-release-gate",
        "policy_strict_gates": "--policy-strict-gates",
        "policy_watch_ci": "--policy-watch-ci",
        "policy_ci_required": "--policy-ci-required",
        "policy_remediate_on_gate_failure": "--policy-remediate-on-gate-failure",
        "policy_release_mode": "--policy-release-mode",
    }
    for key, flag in policy_flags.items():
        command.extend([flag, profile_defaults[key]])

    list_flags = {
        "allowed_file": "--allowed-file",
        "forbidden_file": "--forbidden-file",
        "preserved_component": "--preserved-component",
        "forbidden_change": "--forbidden-change",
        "high_risk_area": "--high-risk-area",
        "controlled_taxonomy": "--controlled-taxonomy",
        "eval_fixture": "--eval-fixture",
        "known_risk": "--known-risk",
    }
    for key, flag in list_flags.items():
        for value in data.get(key, []):
            command.extend([flag, str(value)])

    if sync_state_doc:
        command.append("--sync-state-doc")
    return command


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def configure_agent_provider(data: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(ROOT / "bin" / "configure-agent-provider.py"),
        "--provider",
        str(data["agent_provider"]),
    ]
    if data.get("agent_command"):
        command.extend(["--command", str(data["agent_command"])])
    return run(command)


def decision_policy_for(profile: str) -> dict[str, Any]:
    base = {
        "profile": profile,
        "low_risk": {
            "default_action": "System may decide and act autonomously after recording evidence.",
            "examples": [
                "docs-only correction",
                "formatting/lint-only fix",
                "rerun tests",
                "refresh generated reports",
            ],
        },
        "medium_risk": {
            "default_action": "Research first, record rationale and confidence, then escalate if uncertainty or product impact remains.",
            "confidence_threshold": 0.8,
            "examples": [
                "small current-phase behavior fix",
                "non-breaking regression coverage",
                "limited config change",
            ],
        },
        "high_risk": {
            "default_action": "Human Product Owner approval required before action.",
            "examples": [
                "schema migration",
                "auth/security behavior",
                "external model behavior",
                "user-facing verdict/classification semantics",
                "preserved-component removal",
                "production release",
            ],
        },
    }
    if profile == "human-heavy":
        base["medium_risk"]["confidence_threshold"] = 0.95
        base["medium_risk"]["default_action"] = (
            "Research first, then request human review unless the decision is clearly reversible and low impact."
        )
    if profile == "autonomous-low-risk-only":
        base["medium_risk"]["confidence_threshold"] = 1.0
        base["medium_risk"]["default_action"] = (
            "Do not act autonomously; research and prepare a recommendation for human review."
        )
    return base


def record_intake(
    data: dict[str, Any], command: list[str], applied: bool, ops_check: dict[str, Any] | None
) -> None:
    state = load_state()
    state["setup_intake"] = {
        "last_completed_at": now(),
        "applied": applied,
        "policy_profile": data["policy_profile"],
        "blocker_mode": data["blocker_mode"],
        "human_approval_required": data["human_approval_required"],
        "agent_provider": data["agent_provider"],
        "decision_policy_profile": data["decision_policy_profile"],
        "command": " ".join(shlex.quote(part) for part in command),
        "ops_check_verdict": ops_check.get("verdict") if isinstance(ops_check, dict) else "not-run",
    }
    state["decision_policy"] = decision_policy_for(data["decision_policy_profile"])
    save_state(state)
    log_event("applied" if applied else "planned", data.get("project_name", "TBD"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use supplied values and defaults instead of prompting.",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Run configure-project.py with the collected inputs."
    )
    parser.add_argument(
        "--run-ops-check", action="store_true", help="Run ops-check.py after applying setup."
    )
    parser.add_argument(
        "--strict-ops-check", action="store_true", help="Return nonzero unless ops-check passes."
    )
    parser.add_argument(
        "--print-command", action="store_true", help="Print the configure-project.py command."
    )
    parser.add_argument("--json", action="store_true", help="Print setup intake as JSON.")
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
    parser.add_argument("--blocker-mode", choices=BLOCKER_MODES)
    parser.add_argument("--blocker-recovery-limit", type=int)
    parser.add_argument("--policy-profile", choices=sorted(PROFILE_DEFAULTS))
    parser.add_argument("--agent-provider", choices=AGENT_PROVIDERS)
    parser.add_argument("--agent-command")
    parser.add_argument("--decision-policy-profile", choices=DECISION_POLICY_PROFILES)
    parser.add_argument("--allowed-file", action="append", default=[])
    parser.add_argument("--forbidden-file", action="append", default=[])
    parser.add_argument("--preserved-component", action="append", default=[])
    parser.add_argument("--forbidden-change", action="append", default=[])
    parser.add_argument("--high-risk-area", action="append", default=[])
    parser.add_argument("--controlled-taxonomy", action="append", default=[])
    parser.add_argument("--eval-fixture", action="append", default=[])
    parser.add_argument("--known-risk", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = collect(args)
    command = configure_command(data, sync_state_doc=True)
    ops_check_json: dict[str, Any] | None = None
    configure_result: dict[str, Any] | None = None
    provider_result: dict[str, Any] | None = None
    ops_check_result: dict[str, Any] | None = None
    exit_code = 0

    if args.print_command:
        print(" ".join(shlex.quote(part) for part in command))

    if args.apply:
        result = run(command)
        configure_result = {"exit_code": result.returncode, "stdout": result.stdout}
        if not args.json:
            print(result.stdout, end="")
        if result.returncode != 0:
            exit_code = result.returncode
        else:
            provider = configure_agent_provider(data)
            provider_result = {"exit_code": provider.returncode, "stdout": provider.stdout}
            if not args.json:
                print(provider.stdout, end="")
            if provider.returncode != 0:
                exit_code = provider.returncode
        if exit_code == 0 and args.run_ops_check:
            check_command = [sys.executable, str(ROOT / "bin" / "ops-check.py"), "--json"]
            if args.strict_ops_check:
                check_command.append("--strict")
            check = run(check_command)
            ops_check_result = {"exit_code": check.returncode, "stdout": check.stdout}
            if not args.json:
                print(check.stdout, end="")
            try:
                ops_check_json = json.loads(check.stdout)
            except json.JSONDecodeError:
                ops_check_json = {"verdict": "unparseable", "stdout": check.stdout}
            if check.returncode != 0:
                exit_code = check.returncode
        record_intake(data, command, True, ops_check_json)
    else:
        record_intake(data, command, False, None)

    if args.json:
        output = {
            "setup_intake": data,
            "command": command,
            "applied": args.apply,
            "configure_result": configure_result,
            "provider_result": provider_result,
            "ops_check": ops_check_json,
            "ops_check_result": ops_check_result,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    elif not args.print_command:
        print("Setup intake captured.")
        print(f"Project: {data['project_name']}")
        print(f"Blocker mode: {data['blocker_mode']}")
        print(f"Policy profile: {data['policy_profile']}")
        print(f"Agent provider: {data['agent_provider']}")
        print(f"Decision policy: {data['decision_policy_profile']}")
        print("Next: run with --apply, or review the command with --print-command.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
