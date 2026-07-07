#!/usr/bin/env python3
"""Run a consolidated orchestration operating-system readiness check."""

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
    entry = {"ts": now(), "role": "ops-check", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def run_command(name: str, command: list[str]) -> dict[str, Any]:
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
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "json": parsed,
        "passed": result.returncode == 0,
    }


def verdict_from_step(step: dict[str, Any]) -> str:
    data = step.get("json")
    if isinstance(data, dict):
        for key in ["verdict", "status", "operating_decision", "last_decision"]:
            value = data.get(key)
            if value:
                return str(value)
    if step["passed"]:
        return "PASS"
    return "FAIL"


def build_steps(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    bin_dir = ROOT / "bin"
    steps: list[tuple[str, list[str]]] = [
        ("health-check", [sys.executable, str(bin_dir / "health-check.py"), "--write-report"]),
        (
            "policy-audit",
            [sys.executable, str(bin_dir / "policy-audit.py"), "--write-report", "--json"],
        ),
        (
            "phase-gate",
            [sys.executable, str(bin_dir / "phase-gate.py"), "--write-report", "--json"],
        ),
    ]
    if not args.skip_release_gate:
        steps.append(
            (
                "release-gate",
                [sys.executable, str(bin_dir / "release-gate.py"), "--mode", args.release_mode],
            )
        )
    steps.extend(
        [
            (
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
            (
                "state-doc-sync",
                [sys.executable, str(bin_dir / "sync-state-doc.py"), "--write-report", "--json"],
            ),
            (
                "operating-dashboard",
                [
                    sys.executable,
                    str(bin_dir / "operating-dashboard.py"),
                    "--write-report",
                    "--json",
                    "--events",
                    str(args.events),
                ],
            ),
        ]
    )
    if args.include_acceptance_audit:
        steps.insert(
            1,
            (
                "acceptance-audit",
                [sys.executable, str(bin_dir / "acceptance-audit.py"), "--write-report"],
            ),
        )
    return steps


def build_report(args: argparse.Namespace, steps: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [step for step in steps if not step["passed"]]
    verdict = "PASS" if not failed else "FAIL"
    return {
        "id": f"{compact_ts()}-ops-check",
        "role": "ops-check",
        "status": "completed",
        "verdict": verdict,
        "summary": "Ops check passed."
        if verdict == "PASS"
        else f"Ops check failed: {', '.join(step['name'] for step in failed)}.",
        "created_at": now(),
        "release_mode": args.release_mode,
        "steps": [
            {
                "name": step["name"],
                "exit_code": step["exit_code"],
                "passed": step["passed"],
                "verdict": verdict_from_step(step),
                "command": " ".join(step["command"]),
            }
            for step in steps
        ],
        "failed_steps": [step["name"] for step in failed],
        "recommended_next_action": (
            "Continue with the next authorized action."
            if verdict == "PASS"
            else f"Resolve failed checks: {', '.join(step['name'] for step in failed)}."
        ),
    }


def write_report(state: dict[str, Any], report: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state.setdefault("structured_reports", []).append(str(path.relative_to(ROOT)))
    state["ops_check"] = {
        "last_decision": report["verdict"],
        "last_checked_at": report["created_at"],
        "last_report": str(path.relative_to(ROOT)),
        "failed_steps": report["failed_steps"],
        "recommended_next_action": report["recommended_next_action"],
    }
    save_state(state)
    log_event(report["verdict"], str(path.relative_to(ROOT)))
    return path


def print_text(report: dict[str, Any], report_path: Path | None) -> None:
    print(f"Ops check: {report['verdict']}")
    if report_path:
        print(f"Report: {report_path}")
    for step in report["steps"]:
        print(f"- {step['name']}: {'PASS' if step['passed'] else 'FAIL'} ({step['verdict']})")
    print(f"Next action: {report['recommended_next_action']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-mode", choices=["status", "pr", "merge", "release"], default="status"
    )
    parser.add_argument("--skip-release-gate", action="store_true")
    parser.add_argument("--include-acceptance-audit", action="store_true")
    parser.add_argument("--events", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict", action="store_true", help="Return nonzero unless every step passes."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    steps = [run_command(name, command) for name, command in build_steps(args)]
    state = load_state()
    report = build_report(args, steps)
    report_path = write_report(state, report)
    if args.json:
        output = dict(report)
        output["report_path"] = str(report_path)
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print_text(report, report_path)
    return 1 if args.strict and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
