#!/usr/bin/env python3
"""Classify a decision by risk and enforce the configured autonomy policy."""

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
    return state if isinstance(state, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": "decision-gate", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def default_policy() -> dict[str, Any]:
    return {
        "low_risk": {"default_action": "autonomous", "confidence_threshold": 0.0},
        "medium_risk": {"default_action": "research-first", "confidence_threshold": 0.8},
        "high_risk": {"default_action": "human-required", "confidence_threshold": 1.0},
    }


def build_report(args: argparse.Namespace, state: dict[str, Any]) -> dict[str, Any]:
    policy = (
        state.get("decision_policy")
        if isinstance(state.get("decision_policy"), dict)
        else default_policy()
    )
    bucket = (
        policy.get(f"{args.risk}_risk") if isinstance(policy.get(f"{args.risk}_risk"), dict) else {}
    )
    threshold = float(bucket.get("confidence_threshold", 0.8 if args.risk == "medium" else 0.0))
    confidence = args.confidence if args.confidence is not None else 0.0
    missing: list[str] = []
    decision = "APPROVED_AUTONOMOUS"
    human_required = False

    if not args.decision.strip():
        missing.append("decision")
    if not args.evidence:
        missing.append("evidence")

    if args.risk == "high":
        decision = "HUMAN_REQUIRED"
        human_required = True
    elif args.risk == "medium":
        if not args.research_summary:
            missing.append("research_summary")
        if confidence < threshold or args.human_recommended:
            decision = "HUMAN_RECOMMENDED"
            human_required = args.human_recommended
        else:
            decision = "APPROVED_AFTER_RESEARCH"
    elif missing:
        decision = "REQUEST_EVIDENCE"

    if missing and decision.startswith("APPROVED"):
        decision = "REQUEST_EVIDENCE"

    return {
        "id": f"{compact_ts()}-decision-gate",
        "role": "decision-gate",
        "created_at": now(),
        "risk": args.risk,
        "decision": decision,
        "requested_decision": args.decision,
        "human_required": human_required,
        "confidence": confidence,
        "confidence_threshold": threshold,
        "research_summary": args.research_summary,
        "evidence": args.evidence,
        "missing_evidence": missing,
        "recommended_next_action": recommended_next_action(args.risk, decision),
    }


def recommended_next_action(risk: str, decision: str) -> str:
    if decision == "HUMAN_REQUIRED":
        return "Create or update an approval request and wait for Human Product Owner decision."
    if decision == "HUMAN_RECOMMENDED":
        return "Record the research, then ask a human if uncertainty or product impact remains."
    if decision == "REQUEST_EVIDENCE":
        return "Add the missing evidence before acting."
    if risk == "medium":
        return (
            "Proceed within the authorized phase and record the rationale in the next loop report."
        )
    return "Proceed autonomously and record evidence in the shared state."


def write_report(report: dict[str, Any], open_blocker: bool) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    state = load_state()
    rel_path = str(path.relative_to(ROOT))
    state.setdefault("structured_reports", []).append(rel_path)
    state.setdefault("decision_policy", {})["last_decision"] = report["decision"]
    state.setdefault("decision_policy", {})["last_report"] = rel_path
    if open_blocker and report["decision"] in {
        "HUMAN_REQUIRED",
        "HUMAN_RECOMMENDED",
        "REQUEST_EVIDENCE",
    }:
        state.setdefault("open_blockers", []).append(
            {
                "id": f"blocker-{report['id']}",
                "created_at": report["created_at"],
                "status": "open",
                "severity": "high" if report["human_required"] else "medium",
                "owner": "decision-gate",
                "description": f"Decision gate blocked or escalated: {report['requested_decision']}",
                "evidence": [rel_path],
            }
        )
    save_state(state)
    log_event(report["decision"], rel_path)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--risk", choices=["low", "medium", "high"], required=True)
    parser.add_argument(
        "--decision", required=True, help="The action or decision being considered."
    )
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--research-summary", default="")
    parser.add_argument("--confidence", type=float)
    parser.add_argument("--human-recommended", action="store_true")
    parser.add_argument("--open-blocker", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args, load_state())
    report_path = write_report(report, args.open_blocker)
    if args.json:
        output = dict(report)
        output["report_path"] = str(report_path)
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"Decision: {report['decision']}")
        print(f"Risk: {report['risk']}")
        print(f"Report: {report_path}")
        print(f"Recommended next action: {report['recommended_next_action']}")
    return 1 if report["decision"] in {"HUMAN_REQUIRED", "REQUEST_EVIDENCE"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
