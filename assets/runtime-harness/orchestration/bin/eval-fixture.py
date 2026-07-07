#!/usr/bin/env python3
"""Create and register behavior-level eval fixtures for the orchestration harness."""

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


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return cleaned or f"eval-{compact_ts()}"


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
    entry = {"ts": now(), "role": "eval-fixture", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def read_input(args: argparse.Namespace) -> str:
    if args.input and args.input_file:
        raise SystemExit("Use either --input or --input-file, not both.")
    if args.input_file:
        return Path(args.input_file).read_text()
    return args.input or ""


def parse_expected_json(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--expected-json is not valid JSON: {exc}") from exc


def format_list(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values) if values else "- TBD"


def fixture_markdown(fixture: dict[str, Any]) -> str:
    expected_json = fixture.get("expected_json")
    expected_json_text = (
        "TBD" if expected_json is None else json.dumps(expected_json, indent=2, sort_keys=True)
    )
    return "\n".join(
        [
            f"# Eval Fixture: {fixture['name']}",
            "",
            f"ID: {fixture['id']}",
            f"Created: {fixture['created_at']}",
            f"Phase: {fixture['phase']}",
            f"Owner: {fixture['owner']}",
            f"Source: {fixture['source'] or 'TBD'}",
            "",
            "## Description",
            "",
            fixture["description"] or "TBD",
            "",
            "## Input",
            "",
            "```text",
            fixture["input"] or "TBD",
            "```",
            "",
            "## Expected Behavior",
            "",
            format_list(fixture["expected"]),
            "",
            "## Expected JSON",
            "",
            "```json",
            expected_json_text,
            "```",
            "",
            "## Tolerances",
            "",
            format_list(fixture["tolerances"]),
            "",
            "## Tags",
            "",
            format_list(fixture["tags"]),
            "",
            "## Risks Covered",
            "",
            format_list(fixture["risks"]),
            "",
        ]
    )


def write_report(state: dict[str, Any], fixture: dict[str, Any], fixture_ref: str) -> str:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "id": f"{compact_ts()}-eval-fixture",
        "role": "eval-fixture",
        "status": "completed",
        "verdict": "RECORDED",
        "summary": f"Eval fixture recorded: {fixture['name']}",
        "evidence": fixture_ref,
        "created_at": now(),
        "fixture": fixture,
    }
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state.setdefault("structured_reports", []).append(str(path.relative_to(ROOT)))
    return str(path.relative_to(ROOT))


def cmd_create(args: argparse.Namespace) -> None:
    state = load_state()
    fixture_id = safe_id(args.id or f"eval-{compact_ts()}")
    phase = args.phase or str(state.get("current_phase") or "TBD")
    expected = parse_csv(args.expected)
    if not expected and not args.expected_json:
        raise SystemExit("Provide at least one --expected value or --expected-json.")

    fixture = {
        "id": fixture_id,
        "name": args.name,
        "description": args.description,
        "phase": phase,
        "owner": args.owner,
        "created_at": now(),
        "source": args.source,
        "input": read_input(args),
        "expected": expected,
        "expected_json": parse_expected_json(args.expected_json),
        "tolerances": parse_csv(args.tolerance),
        "tags": parse_csv(args.tag),
        "risks": parse_csv(args.risk),
        "status": "active",
    }

    fixtures_dir = ROOT / "evals" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    json_path = fixtures_dir / f"{fixture_id}.json"
    markdown_path = fixtures_dir / f"{fixture_id}.md"
    if json_path.exists() and not args.replace:
        raise SystemExit(
            f"Eval fixture already exists: {json_path.relative_to(ROOT)}. Use --replace to overwrite."
        )

    json_path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(fixture_markdown(fixture))

    fixture_ref = str(json_path.relative_to(ROOT))
    fixtures = state.setdefault("eval_fixtures", [])
    if not isinstance(fixtures, list):
        raise SystemExit("state.eval_fixtures must be a list.")
    state["eval_fixtures"] = [item for item in fixtures if item != fixture_ref] + [fixture_ref]
    state["last_eval_fixture"] = fixture_ref
    state["eval_quality_status"] = "fixtures-updated"
    watchdog = state.setdefault("watchdog", {})
    if isinstance(watchdog, dict):
        watchdog["eval_quality_status"] = "fixtures-updated"
    if args.write_report:
        state["last_eval_fixture_report"] = write_report(state, fixture, fixture_ref)
    save_state(state)
    log_event("recorded", fixture_ref)

    result = {
        "fixture": fixture_ref,
        "markdown": str(markdown_path.relative_to(ROOT)),
        "report": state.get("last_eval_fixture_report", ""),
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(fixture_ref)


def cmd_list(args: argparse.Namespace) -> None:
    state = load_state()
    refs = state.get("eval_fixtures") or []
    if not isinstance(refs, list):
        raise SystemExit("state.eval_fixtures must be a list.")
    if args.json:
        print(json.dumps(refs, indent=2, sort_keys=True))
    else:
        for ref in refs:
            print(ref)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create and register an eval fixture.")
    create.add_argument("--id", default="", help="Stable fixture id. Generated when omitted.")
    create.add_argument("--name", required=True)
    create.add_argument("--description", default="")
    create.add_argument("--phase", default="", help="Defaults to state.current_phase.")
    create.add_argument("--owner", default="eval-builder")
    create.add_argument(
        "--source", default="", help="Issue, PR, incident, user report, or other evidence source."
    )
    create.add_argument("--input", default="", help="Inline eval input or scenario.")
    create.add_argument("--input-file", default="", help="Path to a file containing eval input.")
    create.add_argument(
        "--expected",
        action="append",
        default=[],
        help="Expected behavior. Repeat or comma-separate.",
    )
    create.add_argument("--expected-json", default="", help="Structured expected behavior as JSON.")
    create.add_argument(
        "--tolerance",
        action="append",
        default=[],
        help="Accepted tolerance. Repeat or comma-separate.",
    )
    create.add_argument(
        "--tag", action="append", default=[], help="Fixture tag. Repeat or comma-separate."
    )
    create.add_argument(
        "--risk",
        action="append",
        default=[],
        help="Risk this fixture protects. Repeat or comma-separate.",
    )
    create.add_argument(
        "--replace", action="store_true", help="Overwrite an existing fixture with the same id."
    )
    create.add_argument(
        "--write-report", action="store_true", help="Write a structured report entry."
    )
    create.add_argument("--json", action="store_true")
    create.set_defaults(func=cmd_create)

    list_cmd = sub.add_parser("list", help="List registered eval fixtures.")
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.set_defaults(func=cmd_list)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
