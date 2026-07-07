#!/usr/bin/env python3
"""Record Eval Monitor actual-vs-expected results as orchestration artifacts."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"

PASS_VERDICTS = {"PASS"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return cleaned or f"eval-result-{compact_ts()}"


def parse_csv(values: list[str]) -> list[str]:
    parsed: list[str] = []
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item:
                parsed.append(item)
    return parsed


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
    entry = {"ts": now(), "role": "eval-result", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def read_optional_file(path: str) -> str:
    if not path:
        return ""
    return Path(path).read_text()


def parse_json_or_text(raw: str, file_path: str) -> Any:
    text = read_optional_file(file_path) if file_path else raw
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def load_fixture(fixture_ref: str) -> dict[str, Any]:
    if not fixture_ref:
        return {}
    path = ROOT / fixture_ref
    if not path.exists():
        path = ROOT / "evals" / "fixtures" / Path(fixture_ref).name
    if not path.exists():
        raise SystemExit(f"Eval fixture not found: {fixture_ref}")
    try:
        fixture = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Eval fixture is not valid JSON: {path}: {exc}") from exc
    if not isinstance(fixture, dict):
        raise SystemExit(f"Eval fixture must contain an object: {path}")
    fixture["artifact_ref"] = str(path.relative_to(ROOT))
    return fixture


def format_value(value: Any) -> str:
    if value is None or value == "":
        return "TBD"
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, sort_keys=True)
    return str(value)


def format_list(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values) if values else "- TBD"


def result_markdown(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# Eval Result: {result['name']}",
            "",
            f"ID: {result['id']}",
            f"Created: {result['created_at']}",
            f"Phase: {result['phase']}",
            f"Fixture: {result['fixture_ref'] or 'TBD'}",
            f"Verdict: {result['verdict']}",
            f"Runner: {result['runner']}",
            f"Command: {result['command'] or 'TBD'}",
            "",
            "## Expected",
            "",
            "```json",
            format_value(result["expected"]),
            "```",
            "",
            "## Actual",
            "",
            "```json",
            format_value(result["actual"]),
            "```",
            "",
            "## Diffs",
            "",
            format_list(result["diffs"]),
            "",
            "## Risks",
            "",
            format_list(result["risks"]),
            "",
            "## Evidence",
            "",
            format_list(result["evidence"]),
            "",
            "## Recommended Next Action",
            "",
            result["recommended_next_action"] or "TBD",
            "",
        ]
    )


def write_report(state: dict[str, Any], result: dict[str, Any], result_ref: str) -> str:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "id": f"{compact_ts()}-eval-result",
        "role": "eval-result",
        "status": "completed",
        "verdict": result["verdict"],
        "summary": f"Eval result recorded: {result['name']} -> {result['verdict']}",
        "evidence": result_ref,
        "created_at": now(),
        "fixture": result.get("fixture_ref", ""),
        "result": result,
    }
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state.setdefault("structured_reports", []).append(str(path.relative_to(ROOT)))
    return str(path.relative_to(ROOT))


def maybe_open_blocker(state: dict[str, Any], result: dict[str, Any], result_ref: str) -> None:
    if result["verdict"] in PASS_VERDICTS:
        return
    state.setdefault("open_blockers", []).append(
        {
            "id": f"blocker-{compact_ts()}",
            "status": "open",
            "severity": result["severity"],
            "owner": "eval-monitor",
            "description": f"Eval {result['verdict']}: {result['name']}",
            "created_at": now(),
            "evidence": result_ref,
            "recommended_next_action": result["recommended_next_action"],
        }
    )


def cmd_record(args: argparse.Namespace) -> None:
    state = load_state()
    fixture = load_fixture(args.fixture) if args.fixture else {}
    result_id = safe_id(args.id or f"eval-result-{compact_ts()}")
    verdict = args.verdict.upper()
    phase = args.phase or str(state.get("current_phase") or "TBD")
    expected = parse_json_or_text(args.expected, args.expected_file)
    if expected is None and fixture:
        expected = {
            "expected": fixture.get("expected", []),
            "expected_json": fixture.get("expected_json"),
            "tolerances": fixture.get("tolerances", []),
        }
    actual = parse_json_or_text(args.actual, args.actual_file)

    result = {
        "id": result_id,
        "name": args.name or fixture.get("name") or result_id,
        "phase": phase,
        "created_at": now(),
        "fixture_ref": fixture.get("artifact_ref", args.fixture),
        "fixture_id": fixture.get("id", ""),
        "runner": args.runner,
        "command": args.command,
        "verdict": verdict,
        "severity": args.severity,
        "expected": expected,
        "actual": actual,
        "diffs": parse_csv(args.diff),
        "risks": parse_csv(args.risk),
        "evidence": parse_csv(args.evidence),
        "recommended_next_action": args.recommended_next_action,
    }

    results_dir = ROOT / "evals" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / f"{result_id}.json"
    markdown_path = results_dir / f"{result_id}.md"
    if json_path.exists() and not args.replace:
        raise SystemExit(f"Eval result already exists: {json_path.relative_to(ROOT)}. Use --replace to overwrite.")

    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(result_markdown(result))

    result_ref = str(json_path.relative_to(ROOT))
    results = state.setdefault("eval_results", [])
    if not isinstance(results, list):
        raise SystemExit("state.eval_results must be a list.")
    state["eval_results"] = [item for item in results if item != result_ref] + [result_ref]
    state["last_eval_result_artifact"] = result_ref
    state["last_eval_result"] = verdict
    state["eval_quality_status"] = "eval-pass" if verdict in PASS_VERDICTS else "eval-attention"
    watchdog = state.setdefault("watchdog", {})
    if isinstance(watchdog, dict):
        watchdog["eval_quality_status"] = state["eval_quality_status"]
    if args.write_report:
        state["last_eval_result_report"] = write_report(state, result, result_ref)
    if args.open_blocker:
        maybe_open_blocker(state, result, result_ref)
    save_state(state)
    log_event("recorded", f"{result_ref} {verdict}")

    output = {
        "result": result_ref,
        "markdown": str(markdown_path.relative_to(ROOT)),
        "report": state.get("last_eval_result_report", ""),
        "verdict": verdict,
    }
    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(result_ref)


def cmd_list(args: argparse.Namespace) -> None:
    state = load_state()
    refs = state.get("eval_results") or []
    if not isinstance(refs, list):
        raise SystemExit("state.eval_results must be a list.")
    if args.json:
        print(json.dumps(refs, indent=2, sort_keys=True))
    else:
        for ref in refs:
            print(ref)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="Record an Eval Monitor result.")
    record.add_argument("--id", default="", help="Stable result id. Generated when omitted.")
    record.add_argument("--name", default="", help="Human-readable result name. Defaults to fixture name.")
    record.add_argument("--fixture", default="", help="Fixture JSON path or id under evals/fixtures.")
    record.add_argument("--phase", default="", help="Defaults to state.current_phase.")
    record.add_argument("--runner", default="eval-monitor")
    record.add_argument("--command", default="", help="Command or procedure used to run the eval.")
    record.add_argument("--verdict", required=True, choices=["PASS", "FAIL", "DRIFT", "BLOCKED", "SKIPPED"])
    record.add_argument("--severity", default="high", choices=["low", "medium", "high", "critical"])
    record.add_argument("--expected", default="", help="Expected output as JSON or text.")
    record.add_argument("--expected-file", default="", help="Read expected output from a file.")
    record.add_argument("--actual", default="", help="Actual output as JSON or text.")
    record.add_argument("--actual-file", default="", help="Read actual output from a file.")
    record.add_argument("--diff", action="append", default=[], help="Observed difference. Repeat or comma-separate.")
    record.add_argument("--risk", action="append", default=[], help="Risk detected or covered. Repeat or comma-separate.")
    record.add_argument("--evidence", action="append", default=[], help="Evidence path, URL, or note. Repeat or comma-separate.")
    record.add_argument("--recommended-next-action", default="")
    record.add_argument("--open-blocker", action="store_true", help="Open a blocker when verdict is not PASS.")
    record.add_argument("--replace", action="store_true", help="Overwrite an existing result with the same id.")
    record.add_argument("--write-report", action="store_true", help="Write a structured report entry.")
    record.add_argument("--json", action="store_true")
    record.set_defaults(func=cmd_record)

    list_cmd = sub.add_parser("list", help="List recorded eval results.")
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.set_defaults(func=cmd_list)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
