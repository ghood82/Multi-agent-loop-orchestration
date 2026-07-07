#!/usr/bin/env python3
"""Audit orchestration operating-system readiness and print the next command."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
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
    entry = {"ts": now(), "role": "doctor", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def run_step(name: str, command: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=ROOT.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    parsed: Any = None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = None
    return {
        "name": name,
        "command": " ".join(command),
        "exit_code": result.returncode,
        "passed": result.returncode == 0,
        "json": parsed,
        "stdout": result.stdout,
    }


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


def get_obj(state: dict[str, Any], key: str) -> dict[str, Any]:
    value = state.get(key)
    return value if isinstance(value, dict) else {}


def provider_summary(provider_json: dict[str, Any] | None, state: dict[str, Any]) -> dict[str, Any]:
    adapter = get_obj(state, "agent_adapter")
    if isinstance(provider_json, dict):
        active = provider_json.get(
            "active_provider", adapter.get("configured_provider", "prompt-only")
        )
        provider = (
            provider_json.get("providers", {}).get(active, {})
            if isinstance(provider_json.get("providers"), dict)
            else {}
        )
    else:
        active = adapter.get("configured_provider", "prompt-only")
        provider = {}
    return {
        "active_provider": active,
        "mode": provider.get("mode", adapter.get("configured_mode", "prompt-only")),
        "command": provider.get("command", adapter.get("configured_command", "")),
        "last_run_provider": adapter.get("last_provider", "TBD"),
        "last_run_role": adapter.get("last_role", "TBD"),
        "last_exit_code": adapter.get("last_exit_code", "TBD"),
    }


def decide(
    state: dict[str, Any], steps: dict[str, dict[str, Any]], provider: dict[str, Any]
) -> tuple[str, str, str]:
    health = steps.get("health-check", {}).get("json") or {}
    status = steps.get("operator-status", {}).get("json") or {}
    resume = steps.get("resume-plan", {}).get("json") or {}
    blockers = open_blockers(state)
    ops_check = get_obj(state, "ops_check")

    if health.get("verdict") == "FAIL":
        return (
            "STOP",
            "Fix harness health failures.",
            "python3 orchestration/bin/health-check.py --write-report",
        )
    if provider.get("active_provider") == "prompt-only":
        return (
            "READY_PROMPT_ONLY",
            "Harness is ready to prepare prompts; configure a provider to execute agents automatically.",
            "python3 orchestration/bin/configure-agent-provider.py --list",
        )
    if blockers:
        return (
            "REMEDIATE",
            f"{len(blockers)} open blocker(s) need handling.",
            "python3 orchestration/bin/resume-plan.py --apply --prefer-remediation --write-report",
        )
    status_decision = str(status.get("operating_decision", "")).upper()
    if status_decision in {"STOP", "REMEDIATE", "WAIT", "RESUME_PLAN"}:
        return (
            status_decision,
            status.get("recommended_next_action", "Follow operator status recommendation."),
            status.get("recommended_next_action", ""),
        )
    resume_decision = str(resume.get("decision", "")).upper()
    if resume_decision in {"REMEDIATE", "WAIT", "PAUSE_FOR_HUMAN", "RERUN_OR_REMEDIATE"}:
        return (
            resume_decision,
            resume.get("next_action", "Follow resume plan."),
            "python3 orchestration/bin/resume-plan.py --apply --write-report",
        )
    if ops_check.get("last_decision") == "FAIL":
        return (
            "CHECK_GATES",
            ops_check.get("recommended_next_action", "Review ops-check findings."),
            "python3 orchestration/bin/ops-check.py --json",
        )
    return (
        "CONTINUE",
        "Run the next authorized role.",
        "bash orchestration/bin/orchestration-daemon.sh --resume-plan --max-steps 1",
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    bin_dir = ROOT / "bin"
    raw_steps = [
        run_step(
            "health-check", [sys.executable, str(bin_dir / "health-check.py"), "--write-report"]
        ),
        run_step(
            "provider-list",
            [sys.executable, str(bin_dir / "configure-agent-provider.py"), "--list", "--json"],
        ),
        run_step(
            "operator-status",
            [
                sys.executable,
                str(bin_dir / "status.py"),
                "--write-report",
                "--json",
                "--events",
                str(args.events),
            ],
        ),
        run_step(
            "resume-plan", [sys.executable, str(bin_dir / "resume-plan.py"), "--write-report"]
        ),
    ]
    if args.run_ops_check:
        command = [
            sys.executable,
            str(bin_dir / "ops-check.py"),
            "--json",
            "--events",
            str(args.events),
        ]
        if args.strict_ops_check:
            command.append("--strict")
        raw_steps.append(run_step("ops-check", command))
    state = load_state()
    steps = {step["name"]: step for step in raw_steps}
    provider = provider_summary(steps.get("provider-list", {}).get("json"), state)
    decision, reason, next_command = decide(state, steps, provider)
    health = steps.get("health-check", {}).get("json") or {}
    status = steps.get("operator-status", {}).get("json") or {}
    resume = steps.get("resume-plan", {}).get("json") or {}
    return {
        "id": f"{compact_ts()}-doctor",
        "role": "doctor",
        "status": "completed",
        "verdict": decision,
        "summary": reason,
        "created_at": now(),
        "project": {
            "name": state.get("project_name", "TBD"),
            "repo": state.get("repo", "TBD"),
            "phase": state.get("current_phase", "TBD"),
            "objective": state.get("current_objective", "TBD"),
        },
        "provider": provider,
        "health": {
            "verdict": health.get("verdict", "TBD"),
            "failures": health.get("failures", []),
            "warnings": health.get("warnings", []),
        },
        "blockers": {
            "count": len(open_blockers(state)),
            "items": open_blockers(state),
        },
        "operator_status": {
            "decision": status.get("operating_decision", "TBD"),
            "recommended_next_action": status.get("recommended_next_action", "TBD"),
        },
        "resume_plan": {
            "decision": resume.get("decision", "TBD"),
            "next_role": resume.get("next_role", "TBD"),
            "next_action": resume.get("next_action", "TBD"),
        },
        "ops_check": get_obj(state, "ops_check"),
        "next_command": next_command,
        "steps": [
            {
                "name": step["name"],
                "exit_code": step["exit_code"],
                "passed": step["passed"],
                "command": step["command"],
            }
            for step in raw_steps
        ],
    }


def write_report(report: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state = load_state()
    rel = str(path.relative_to(ROOT))
    state.setdefault("structured_reports", []).append(rel)
    state["doctor"] = {
        "last_decision": report["verdict"],
        "last_checked_at": report["created_at"],
        "last_report": rel,
        "summary": report["summary"],
        "next_command": report["next_command"],
    }
    save_state(state)
    log_event(report["verdict"], rel)
    return path


def print_text(report: dict[str, Any], report_path: Path | None) -> None:
    print("# Orchestration Doctor")
    print(f"Project: {report['project']['name']}")
    print(f"Phase: {report['project']['phase']}")
    print(f"Decision: {report['verdict']}")
    print(f"Reason: {report['summary']}")
    print(f"Next command: {report['next_command']}")
    if report_path:
        print(f"Report: {report_path}")
    print()
    print("## Checks")
    print(f"- Health: {report['health']['verdict']}")
    print(f"- Provider: {report['provider']['active_provider']} ({report['provider']['mode']})")
    print(f"- Open blockers: {report['blockers']['count']}")
    print(f"- Operator status: {report['operator_status']['decision']}")
    print(f"- Resume plan: {report['resume_plan']['decision']}")
    print(f"- Ops check: {report['ops_check'].get('last_decision', 'TBD')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=5)
    parser.add_argument("--run-ops-check", action="store_true")
    parser.add_argument("--strict-ops-check", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict", action="store_true", help="Return nonzero unless doctor verdict is CONTINUE."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    report_path = write_report(report) if args.write_report else None
    if args.json:
        output = dict(report)
        if report_path:
            output["report_path"] = str(report_path)
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print_text(report, report_path)
    if args.strict and report["verdict"] != "CONTINUE":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
