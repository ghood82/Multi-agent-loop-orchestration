#!/usr/bin/env python3
"""Normalize role markdown reports into structured state.

This parser is intentionally conservative. It records structured evidence from
free-form role reports and opens blockers only when the report explicitly says
the work is blocked, failed, stopped, requests fixes, or lists blockers.
"""

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

ROLES = {
    "builder",
    "qa",
    "security",
    "eval-builder",
    "eval",
    "watchdog",
    "remediation",
    "architect",
    "docs",
    "subagent",
}

LAST_RESULT_FIELDS = {
    "builder": "last_builder_result",
    "qa": "last_qa_result",
    "security": "last_security_result",
    "eval-builder": "last_eval_builder_result",
    "eval": "last_eval_result",
    "watchdog": "last_watchdog_verdict",
    "remediation": "last_remediation_result",
    "architect": "last_architect_decision",
    "docs": "last_documentation_update",
}

NEGATIVE_VERDICTS = {
    "BLOCKED",
    "FAIL",
    "FAILED",
    "REQUEST_FIXES",
    "REQUEST_CHANGES",
    "PROCESS_WARNING",
    "STOP",
}

POSITIVE_VERDICTS = {
    "APPROVE": "PASS",
    "APPROVED": "PASS",
    "PASS": "PASS",
    "PASSED": "PASS",
}

VERDICT_ALIASES = {
    **POSITIVE_VERDICTS,
    "REQUEST FIXES": "REQUEST_FIXES",
    "REQUEST_CHANGES": "REQUEST_FIXES",
    "REQUEST CHANGES": "REQUEST_FIXES",
    "NEEDS_FIXES": "REQUEST_FIXES",
    "NEEDS FIXES": "REQUEST_FIXES",
    "PROCESS WARNING": "PROCESS_WARNING",
    "BLOCKED": "BLOCKED",
    "FAIL": "FAIL",
    "FAILED": "FAIL",
    "STOP": "STOP",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize orchestration markdown reports.")
    parser.add_argument("reports", nargs="+", help="Markdown report paths.")
    parser.add_argument(
        "--open-blockers",
        action="store_true",
        help="Open state blockers for explicit negative verdicts or listed blockers.",
    )
    parser.add_argument(
        "--role",
        choices=sorted(ROLES),
        default="",
        help="Override role detection for all provided reports.",
    )
    return parser.parse_args()


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON: {exc}") from exc


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(role: str, event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": role, "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def detect_role(path: Path, text: str, override: str = "") -> str:
    if override:
        return override
    name = path.stem.lower()
    for role in sorted(ROLES, key=len, reverse=True):
        if name.endswith(f"-{role}") or role in name:
            return role
    heading = re.search(r"^#\s+([a-z-]+)\s+report\b", text, re.IGNORECASE | re.MULTILINE)
    if heading and heading.group(1).lower() in ROLES:
        return heading.group(1).lower()
    return "docs"


def normalize_verdict(raw: str) -> str:
    cleaned = raw.strip().upper().replace("-", "_")
    cleaned = re.sub(r"[^A-Z_ ]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned in VERDICT_ALIASES:
        return VERDICT_ALIASES[cleaned]
    underscored = cleaned.replace(" ", "_")
    return VERDICT_ALIASES.get(underscored, underscored)


def first_field(text: str, names: list[str]) -> str:
    pattern = "|".join(re.escape(name) for name in names)
    match = re.search(
        rf"^\s*(?:[-*]\s*)?(?:{pattern})\s*:\s*(.+?)\s*$",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def detect_exit_code(text: str) -> int | None:
    raw = first_field(text, ["Exit code"])
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def detect_verdict(text: str) -> str:
    raw = first_field(
        text,
        [
            "Watchdog verdict",
            "Verdict",
            "Recommendation",
            "Decision",
            "Result",
        ],
    )
    if raw:
        first_token = raw.split(".", 1)[0].split(",", 1)[0].strip()
        verdict = normalize_verdict(first_token)
        if verdict:
            return verdict

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        verdict = normalize_verdict(stripped.lstrip("-* "))
        if verdict in NEGATIVE_VERDICTS or verdict == "PASS":
            return verdict
    return ""


def detect_status(text: str, verdict: str) -> str:
    raw = first_field(text, ["Status"])
    if raw:
        return normalize_verdict(raw).lower()
    exit_code = detect_exit_code(text)
    if exit_code is not None and exit_code != 0:
        return "failed"
    if verdict in NEGATIVE_VERDICTS:
        return "blocked" if verdict == "BLOCKED" else "needs_attention"
    if verdict == "PASS":
        return "completed"
    if exit_code == 0:
        return "completed"
    return "observed"


def capture_section_items(text: str, headings: list[str]) -> list[str]:
    heading_pattern = "|".join(re.escape(heading) for heading in headings)
    match = re.search(
        rf"^\s*(?:#+\s*)?(?:{heading_pattern})\s*:?\s*$",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        inline = first_field(text, headings)
        return [inline] if inline else []

    start = match.end()
    rest = text[start:]
    next_heading = re.search(
        r"^\s*(?:#{1,6}\s+\S|[A-Za-z][A-Za-z /_-]{1,60}:\s*$)", rest, re.MULTILINE
    )
    section = rest[: next_heading.start()] if next_heading else rest
    items: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^[-*]\s+", "", stripped).strip()
        if stripped and stripped.upper() not in {"NONE", "N/A", "NA", "TBD"}:
            items.append(stripped)
    return items


def detect_summary(text: str) -> str:
    summary = first_field(text, ["Summary", "Verification summary", "Implementation summary"])
    if summary:
        return summary
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("```"):
            return stripped[:500]
    return ""


def blocker_exists(state: dict[str, Any], description: str, source_report: str) -> bool:
    for blocker in state.get("open_blockers", []) or []:
        if not isinstance(blocker, dict):
            continue
        if (
            blocker.get("description") == description
            and blocker.get("source_report") == source_report
        ):
            return True
    return False


def add_blocker(
    state: dict[str, Any],
    role: str,
    description: str,
    source_report: str,
    severity: str = "medium",
) -> None:
    if not description or blocker_exists(state, description, source_report):
        return
    blocker = {
        "id": f"blocker-{compact_ts()}-{len(state.get('open_blockers', []) or []) + 1}",
        "status": "open",
        "severity": severity,
        "owner": role,
        "description": description,
        "created_at": now(),
        "evidence": f"Extracted from {source_report}",
        "source_report": source_report,
    }
    state.setdefault("open_blockers", []).append(blocker)


def normalize_report(path: Path, role_override: str = "") -> dict[str, Any]:
    text = path.read_text(errors="replace")
    role = detect_role(path, text, role_override)
    verdict = detect_verdict(text)
    status = detect_status(text, verdict)
    rel_source = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    blockers = capture_section_items(
        text, ["Open blockers", "Blockers", "Required fixes", "Stop reason"]
    )
    tests = capture_section_items(text, ["Tests run", "Tests/checks run", "Checks run"])
    files = capture_section_items(text, ["Files changed", "Files involved", "Files reviewed"])
    risks = capture_section_items(text, ["Risks", "Regression risks", "Security/privacy findings"])

    report = {
        "id": f"{compact_ts()}-{role}",
        "role": role,
        "status": status,
        "verdict": verdict,
        "summary": detect_summary(text),
        "evidence": rel_source,
        "created_at": now(),
        "source_report": rel_source,
        "exit_code": detect_exit_code(text),
        "blockers": blockers,
        "tests": tests,
        "files": files,
        "risks": risks,
    }
    return report


def write_report(report: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report['id']}.json"
    suffix = 1
    while path.exists():
        suffix += 1
        path = reports_dir / f"{compact_ts()}-{suffix}-{report['role']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return path


def apply_report_to_state(
    state: dict[str, Any], report: dict[str, Any], report_path: Path, open_blockers: bool
) -> None:
    rel_report = str(report_path.relative_to(ROOT))
    if rel_report not in state.setdefault("structured_reports", []):
        state["structured_reports"].append(rel_report)

    role = str(report["role"])
    field = LAST_RESULT_FIELDS.get(role)
    if field:
        state[field] = report.get("verdict") or report.get("status") or "observed"
    if role == "watchdog":
        state.setdefault("watchdog", {})["last_verdict"] = report.get("verdict") or report.get(
            "status"
        )

    if not open_blockers:
        return

    verdict = str(report.get("verdict") or "").upper()
    source = str(report.get("source_report") or rel_report)
    for blocker in report.get("blockers") or []:
        add_blocker(state, role, str(blocker), source)
    if verdict in NEGATIVE_VERDICTS:
        summary = report.get("summary") or f"{role} reported {verdict}"
        severity = "high" if verdict in {"STOP", "FAIL", "FAILED"} else "medium"
        add_blocker(state, role, f"{role} verdict {verdict}: {summary}", source, severity=severity)


def main() -> int:
    args = parse_args()
    state = load_state()
    output_paths: list[Path] = []
    for raw_path in args.reports:
        path = Path(raw_path)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        report = normalize_report(path, args.role)
        report_path = write_report(report)
        apply_report_to_state(state, report, report_path, args.open_blockers)
        output_paths.append(report_path)
        log_event(report["role"], "report_normalized", str(report_path.relative_to(ROOT)))
    save_state(state)
    for path in output_paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
