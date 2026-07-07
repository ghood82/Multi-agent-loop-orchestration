#!/usr/bin/env python3
"""Create a Human Product Owner approval request artifact."""

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
    entry = {"ts": now(), "role": "approval-request", "event": event, "note": note}
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


def markdown(request: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Human Approval Request",
            "",
            f"Scope: {request['scope']}",
            f"Requested decision: {request['requested_decision']}",
            f"Requested by: {request['requested_by']}",
            f"Created at: {request['created_at']}",
            "",
            "## Reason",
            "",
            request["reason"] or "TBD",
            "",
            "## Evidence",
            "",
            bullet_list(request["evidence"]),
            "",
            "## Risks",
            "",
            bullet_list(request["risks"]),
            "",
            "## Options",
            "",
            bullet_list(request["options"]),
            "",
            "## Recommendation",
            "",
            request["recommendation"] or "TBD",
            "",
            "## Human Decision Needed",
            "",
            request["human_decision_needed"],
            "",
        ]
    )


def create_request(args: argparse.Namespace) -> tuple[dict[str, Any], Path, Path]:
    state = load_state()
    request_id = f"approval-request-{compact_ts()}"
    request = {
        "id": request_id,
        "type": "approval_request",
        "status": "requested",
        "scope": args.scope,
        "requested_decision": args.requested_decision,
        "requested_by": args.requested_by,
        "reason": args.reason,
        "evidence": split_values(args.evidence),
        "risks": split_values(args.risk),
        "options": split_values(args.option),
        "recommendation": args.recommendation,
        "human_decision_needed": args.human_decision_needed,
        "created_at": now(),
    }

    requests_dir = ROOT / "approvals" / "requests"
    reports_dir = ROOT / "reports" / "json"
    requests_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = requests_dir / f"{request_id}.md"
    json_path = requests_dir / f"{request_id}.json"
    markdown_path.write_text(markdown(request))
    json_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")

    rel_markdown = str(markdown_path.relative_to(ROOT))
    rel_json = str(json_path.relative_to(ROOT))
    state.setdefault("approval_requests", []).append(rel_json)
    state["last_approval_request"] = rel_json
    state["next_authorized_action"] = args.next_authorized_action or f"Human decision required for: {args.scope}"

    report = {
        "id": f"{compact_ts()}-approval-request",
        "role": "approval-request",
        "status": "requested",
        "verdict": "HUMAN_DECISION_REQUIRED",
        "summary": args.scope,
        "created_at": now(),
        "approval_request": rel_json,
        "markdown": rel_markdown,
    }
    report_path = reports_dir / f"{report['id']}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state.setdefault("structured_reports", []).append(str(report_path.relative_to(ROOT)))

    if args.open_blocker:
        blocker = {
            "id": f"blocker-{compact_ts()}",
            "status": "open",
            "severity": args.severity,
            "owner": "human-product-owner",
            "description": f"Human approval required: {args.scope}",
            "created_at": now(),
            "evidence": rel_markdown,
        }
        state.setdefault("open_blockers", []).append(blocker)

    save_state(state)
    log_event("requested", rel_json)
    return request, markdown_path, json_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--requested-decision", default="approve or reject")
    parser.add_argument("--requested-by", default="orchestration")
    parser.add_argument("--reason", default="")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--risk", action="append", default=[])
    parser.add_argument("--option", action="append", default=[])
    parser.add_argument("--recommendation", default="")
    parser.add_argument("--human-decision-needed", default="yes", choices=["yes", "no", "true", "false"])
    parser.add_argument("--next-authorized-action", default="")
    parser.add_argument("--open-blocker", action="store_true")
    parser.add_argument("--severity", default="high")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    request, markdown_path, json_path = create_request(args)
    if args.json:
        print(json.dumps({"request": request, "markdown": str(markdown_path), "json": str(json_path)}, indent=2, sort_keys=True))
    else:
        print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
