#!/usr/bin/env python3
"""Prepare the evidence packet Watchdog must review before issuing a verdict."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"
RUBRIC = ROOT / "evals" / "rubrics" / "project-quality-rubric.md"


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
    return state if isinstance(state, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": "prepare-watchdog-evidence", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def meaningful(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.upper() not in {"TBD", "NONE", "N/A", "NA", "[]"}


def run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return (
        result.stdout.strip()
        if result.returncode == 0
        else f"git {' '.join(args)} failed: {result.stdout.strip()}"
    )


def ensure_rubric() -> None:
    if RUBRIC.exists():
        return
    RUBRIC.parent.mkdir(parents=True, exist_ok=True)
    RUBRIC.write_text(
        "# Project Quality Rubric\n\n"
        "Use this rubric before Watchdog gives a final verdict.\n\n"
        "## Objective Fit\n\n- Change serves the current objective.\n- Change stays inside the authorized phase.\n\n"
        "## Connected Tests\n\n- Primary test command: `[TBD]`\n- Required CI/PR checks: `[TBD]`\n\n"
        "## Behavior Evals\n\n- Required eval fixtures: `[TBD]`\n- Drift signals: classifications, counts, confidence, extracted fields, verdicts, model/API payloads.\n\n"
        "## Decision Policy\n\n- Low risk: autonomous with evidence.\n- Medium risk: research first.\n- High risk: human approval required.\n"
    )


def existing_refs(state: dict[str, Any], key: str) -> list[str]:
    value = state.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if meaningful(item)]


def latest_reports(limit: int = 12) -> list[str]:
    reports: list[Path] = []
    for base in [ROOT / "reports", ROOT / "reports" / "json", ROOT / "reports" / "subagents"]:
        if base.exists():
            reports.extend(path for path in base.glob("*") if path.is_file())
    reports = sorted(reports, key=lambda path: path.stat().st_mtime)
    return [str(path.relative_to(ROOT)) for path in reports[-limit:]]


def build_packet(args: argparse.Namespace) -> dict[str, Any]:
    if not args.no_bootstrap:
        ensure_rubric()
    state = load_state()
    connected_tests = existing_refs(state, "connected_tests")
    test_command = state.get("test_command")
    if meaningful(test_command) and str(test_command) not in connected_tests:
        connected_tests.append(str(test_command))

    eval_fixtures = existing_refs(state, "eval_fixtures")
    eval_results = existing_refs(state, "eval_results")
    missing = []
    if not RUBRIC.exists():
        missing.append("quality rubric")
    if not connected_tests:
        missing.append("connected tests")
    if not eval_fixtures:
        missing.append("eval fixtures")
    if not eval_results:
        missing.append("eval results")

    diff_report = {
        "status_short": run_git(["status", "--short"]),
        "diff_stat": run_git(["diff", "--stat"]),
        "diff_files": run_git(["diff", "--name-only"]).splitlines(),
        "head": run_git(["rev-parse", "--short", "HEAD"]),
        "branch": run_git(["branch", "--show-current"]),
    }
    verdict = "PASS" if not missing else "WARN"
    return {
        "id": f"{compact_ts()}-watchdog-evidence",
        "role": "prepare-watchdog-evidence",
        "created_at": now(),
        "verdict": verdict,
        "summary": "Watchdog evidence prepared."
        if verdict == "PASS"
        else "Watchdog evidence prepared with gaps.",
        "missing_evidence": missing,
        "quality_rubric": str(RUBRIC.relative_to(ROOT)) if RUBRIC.exists() else "missing",
        "connected_tests": connected_tests,
        "eval_fixtures": eval_fixtures,
        "eval_results": eval_results,
        "latest_reports": latest_reports(),
        "pr_diff": diff_report,
        "recommended_next_action": "Run Watchdog."
        if verdict == "PASS"
        else "Assign Eval Builder/Eval Monitor or project setup to close missing evidence before Watchdog PASS.",
    }


def write_report(packet: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{packet['id']}.json"
    path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")

    state = load_state()
    rel_path = str(path.relative_to(ROOT))
    state.setdefault("structured_reports", []).append(rel_path)
    state["connected_tests"] = packet["connected_tests"]
    if packet["quality_rubric"] != "missing":
        rubrics = state.setdefault("quality_rubrics", [])
        if packet["quality_rubric"] not in rubrics:
            rubrics.append(packet["quality_rubric"])
    state.setdefault("pr_diff_reports", []).append(rel_path)
    state["watchdog_evidence"] = {
        "last_verdict": packet["verdict"],
        "last_prepared_at": packet["created_at"],
        "last_report": rel_path,
        "missing_evidence": packet["missing_evidence"],
        "connected_tests": packet["connected_tests"],
        "eval_fixtures": packet["eval_fixtures"],
        "eval_results": packet["eval_results"],
        "pr_diff_report": rel_path,
        "quality_rubric": packet["quality_rubric"],
    }
    save_state(state)
    log_event(packet["verdict"], rel_path)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero unless the evidence packet is complete.",
    )
    parser.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Do not create a starter quality rubric when missing.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    packet = build_packet(args)
    report_path = write_report(packet) if args.write_report else None
    if args.json:
        output = dict(packet)
        if report_path:
            output["report_path"] = str(report_path)
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"Verdict: {packet['verdict']}")
        if report_path:
            print(f"Report: {report_path}")
        if packet["missing_evidence"]:
            print("Missing evidence:")
            for item in packet["missing_evidence"]:
                print(f"- {item}")
    return 1 if args.strict and packet["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
