#!/usr/bin/env python3
"""Create a structured stop report and optional blocker."""

from __future__ import annotations

import argparse
import json
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
    entry = {"ts": now(), "role": "stop-report", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def split_values(values: list[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        for part in value.split(","):
            text = part.strip()
            if text:
                items.append(text)
    return items


def bullet_list(values: list[str]) -> str:
    if not values:
        return "- TBD"
    return "\n".join(f"- {value}" for value in values)


def markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Stop Report",
            "",
            f"Stop reason: {report['stop_reason']}",
            f"Current phase: {report['current_phase']}",
            "Files involved:",
            bullet_list(report["files_involved"]),
            "",
            "What changed:",
            report["what_changed"] or "TBD",
            "",
            "What failed:",
            report["what_failed"] or "TBD",
            "",
            "Tests run:",
            bullet_list(report["tests_run"]),
            "",
            "Risks:",
            bullet_list(report["risks"]),
            "",
            "Recommended next action:",
            report["recommended_next_action"] or "TBD",
            "",
            f"Human decision needed: {report['human_decision_needed']}",
            "",
        ]
    )


def create_stop_report(args: argparse.Namespace) -> tuple[dict[str, Any], Path, Path]:
    state = load_state()
    reports_dir = ROOT / "reports"
    json_dir = reports_dir / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    report_id = f"{compact_ts()}-stop-report"
    report = {
        "id": report_id,
        "role": "stop-report",
        "status": "stopped",
        "verdict": "STOP",
        "summary": args.stop_reason,
        "created_at": now(),
        "stop_reason": args.stop_reason,
        "current_phase": args.current_phase or state.get("current_phase", "TBD"),
        "files_involved": split_values(args.file),
        "what_changed": args.what_changed,
        "what_failed": args.what_failed,
        "tests_run": split_values(args.test),
        "risks": split_values(args.risk),
        "recommended_next_action": args.recommended_next_action,
        "human_decision_needed": args.human_decision_needed,
        "owner": args.owner,
        "severity": args.severity,
    }

    markdown_path = reports_dir / f"{report_id}.md"
    json_path = json_dir / f"{report_id}.json"
    markdown_path.write_text(markdown(report))
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    rel_json = str(json_path.relative_to(ROOT))
    rel_markdown = str(markdown_path.relative_to(ROOT))
    state.setdefault("structured_reports", []).append(rel_json)
    state.setdefault("stop_reports", []).append(rel_markdown)
    state["last_stop_report"] = rel_markdown
    state["next_authorized_action"] = args.recommended_next_action or "Human decision required before continuing."

    if args.open_blocker:
        blocker = {
            "id": f"blocker-{compact_ts()}",
            "status": "open",
            "severity": args.severity,
            "owner": args.owner,
            "description": f"Stop report: {args.stop_reason}",
            "created_at": now(),
            "evidence": rel_markdown,
        }
        state.setdefault("open_blockers", []).append(blocker)

    save_state(state)
    log_event("created", rel_markdown)
    return report, markdown_path, json_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop-reason", required=True)
    parser.add_argument("--current-phase", default="")
    parser.add_argument("--file", action="append", default=[], help="File involved. May be repeated or comma-separated.")
    parser.add_argument("--what-changed", default="")
    parser.add_argument("--what-failed", default="")
    parser.add_argument("--test", action="append", default=[], help="Test command/result. May be repeated or comma-separated.")
    parser.add_argument("--risk", action="append", default=[], help="Risk. May be repeated or comma-separated.")
    parser.add_argument("--recommended-next-action", default="")
    parser.add_argument("--human-decision-needed", default="yes", choices=["yes", "no", "true", "false"])
    parser.add_argument("--owner", default="human-product-owner")
    parser.add_argument("--severity", default="high")
    parser.add_argument("--open-blocker", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report, markdown_path, json_path = create_stop_report(args)
    if args.json:
        print(json.dumps({"report": report, "markdown": str(markdown_path), "json": str(json_path)}, indent=2, sort_keys=True))
    else:
        print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
