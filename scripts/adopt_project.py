#!/usr/bin/env python3
"""Install and configure the orchestration runtime in a target repository."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
CREATE_HARNESS = SKILL_ROOT / "scripts" / "create_runtime_harness.py"


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def fail(label: str, result: subprocess.CompletedProcess[str]) -> None:
    raise SystemExit(f"{label} failed with exit code {result.returncode}\n{result.stdout}")


def load_state(target: Path) -> dict[str, Any]:
    state_path = target / "orchestration" / "state.json"
    try:
        state = json.loads(state_path.read_text())
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing generated state file: {state_path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid generated state JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise SystemExit("Generated state.json must contain an object.")
    return state


def setup_command(args: argparse.Namespace, target: Path) -> list[str]:
    command = [
        sys.executable,
        str(target / "orchestration" / "bin" / "setup-intake.py"),
        "--non-interactive",
        "--apply",
        "--run-ops-check",
        "--json",
    ]
    if args.strict_readiness:
        command.append("--strict-ops-check")

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
        "blocker_recovery_limit": "--blocker-recovery-limit",
        "policy_profile": "--policy-profile",
    }
    for key, flag in scalar_flags.items():
        value = getattr(args, key)
        if value is not None:
            command.extend([flag, str(value)])

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
        for value in getattr(args, key):
            command.extend([flag, str(value)])
    return command


def create_harness_command(args: argparse.Namespace, target: Path) -> list[str]:
    command = [
        sys.executable,
        str(CREATE_HARNESS),
        "--target",
        str(target),
        "--project-name",
        args.project_name or "TBD",
        "--repo-name",
        args.repo_name or target.name,
        "--roadmap-name",
        args.roadmap_name or "TBD",
        "--current-phase",
        args.current_phase or "TBD",
        "--current-objective",
        args.current_objective or "TBD",
        "--state-file-path",
        args.state_file_path,
        "--test-command",
        args.test_command or "TBD",
    ]
    if args.force:
        command.append("--force")
    if args.install_hooks is False:
        command.append("--no-install-hooks")
    elif args.install_hooks is True:
        command.append("--install-hooks")
    return command


def parse_json_stdout(stdout: str) -> dict[str, Any]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        return {"unparsed_stdout": stdout}
    return value if isinstance(value, dict) else {"value": value}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=".", help="Target repository root.")
    parser.add_argument(
        "--force", action="store_true", help="Overwrite an existing orchestration harness."
    )
    parser.add_argument(
        "--install-hooks",
        dest="install_hooks",
        action="store_true",
        default=None,
        help="Install the write-lock git hook. Default: on when the target is a git repo.",
    )
    parser.add_argument(
        "--no-install-hooks",
        dest="install_hooks",
        action="store_false",
        help="Skip installing the write-lock git hook.",
    )
    parser.add_argument(
        "--strict-readiness",
        action="store_true",
        help="Fail adoption unless the consolidated ops check passes.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable adoption output."
    )
    parser.add_argument("--project-name")
    parser.add_argument("--repo-name")
    parser.add_argument("--roadmap-name")
    parser.add_argument("--current-phase")
    parser.add_argument("--current-objective")
    parser.add_argument("--state-file-path", default="docs/project-roadmap-state.md")
    parser.add_argument("--active-branch")
    parser.add_argument("--active-pr")
    parser.add_argument("--test-command")
    parser.add_argument(
        "--human-approval-required",
        choices=["true", "false", "yes", "no", "1", "0", "required", "not-required"],
    )
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
    parser.add_argument("--policy-profile", choices=["standard", "strict-pr"])
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
    target = Path(args.target).resolve()
    target.mkdir(parents=True, exist_ok=True)

    create_result = run(create_harness_command(args, target), SKILL_ROOT)
    if create_result.returncode != 0:
        fail("Harness creation", create_result)

    setup_result = run(setup_command(args, target), target)
    if setup_result.returncode != 0:
        fail("Setup intake", setup_result)

    status_result = run(
        [
            sys.executable,
            str(target / "orchestration" / "bin" / "status.py"),
            "--write-report",
            "--json",
        ],
        target,
    )
    if status_result.returncode != 0:
        fail("Operator status", status_result)

    handoff_result = run(
        [
            sys.executable,
            str(target / "orchestration" / "bin" / "handoff-packet.py"),
            "--role",
            "builder",
            "--write",
            "--write-report",
            "--json",
        ],
        target,
    )
    if handoff_result.returncode != 0:
        fail("Builder handoff packet", handoff_result)

    state = load_state(target)
    setup_json = parse_json_stdout(setup_result.stdout)
    status_json = parse_json_stdout(status_result.stdout)
    handoff_json = parse_json_stdout(handoff_result.stdout)
    output = {
        "target": str(target),
        "created": True,
        "project": state.get("project_name", "TBD"),
        "current_phase": state.get("current_phase", "TBD"),
        "current_objective": state.get("current_objective", "TBD"),
        "next_authorized_action": state.get("next_authorized_action", "TBD"),
        "ops_check": state.get("ops_check", {}),
        "operator_status": state.get("operator_status", {}),
        "builder_handoff": handoff_json,
        "setup_intake": state.get("setup_intake", {}),
        "setup_output": setup_json,
        "status_output": status_json,
    }

    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"Orchestration adopted in: {target}")
        print(f"Project: {output['project']}")
        print(f"Current phase: {output['current_phase']}")
        print(f"Ops check: {output['ops_check'].get('last_decision', 'TBD')}")
        print(f"Operator decision: {output['operator_status'].get('last_decision', 'TBD')}")
        print(f"Next Builder assignment: {output['next_authorized_action']}")
        if handoff_json.get("path"):
            print(f"Builder handoff packet: {handoff_json['path']}")
        print(
            "Run next: bash orchestration/bin/orchestration-daemon.sh --resume-plan --max-steps 1"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
