#!/usr/bin/env python3
"""Dispatch read-only specialist subagents and record their findings."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"
DEFAULT_MANIFEST = ROOT / "subagents" / "manifest.json"

NEGATIVE_VERDICTS = {"BLOCKED", "FAIL", "FAILED", "REQUEST_FIXES", "REQUEST_CHANGES", "PROCESS_WARNING", "STOP"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch read-only orchestration subagents.")
    parser.add_argument("--role", required=True, help="Parent loop role requesting specialist review.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--agent-command", default="", help="Provider command passed to agent-adapter.py.")
    parser.add_argument("--agent-id", action="append", default=[], help="Run only this subagent id. Repeatable.")
    parser.add_argument("--open-blockers", action="store_true", help="Open blockers for explicit negative subagent verdicts/findings.")
    parser.add_argument("--fail-on-negative", action="store_true", help="Exit non-zero if any subagent returns a negative verdict.")
    parser.add_argument("--disable-file-guard", action="store_true", help="Disable subagent read-only file guard.")
    parser.add_argument("--no-file-guard-blocker", action="store_true", help="Do not open blockers for subagent file guard violations.")
    return parser.parse_args()


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON: {exc}") from exc


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid subagent manifest JSON: {exc}") from exc
    if not isinstance(manifest.get("subagents"), list):
        raise SystemExit("Subagent manifest must contain a subagents list.")
    return manifest


def log_event(role: str, event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": role, "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def select_subagents(manifest: dict[str, Any], role: str, agent_ids: list[str]) -> list[dict[str, Any]]:
    selected = []
    requested = set(agent_ids)
    for subagent in manifest.get("subagents", []):
        if not isinstance(subagent, dict) or not subagent.get("enabled", True):
            continue
        subagent_id = str(subagent.get("id", ""))
        parent_roles = {str(item) for item in subagent.get("parent_roles", [])}
        if requested and subagent_id not in requested:
            continue
        if not requested and role not in parent_roles:
            continue
        selected.append(subagent)
    return selected


def state_snapshot(state: dict[str, Any]) -> str:
    keys = [
        "project_name",
        "repo",
        "roadmap",
        "current_phase",
        "current_objective",
        "active_branch",
        "active_pr",
        "write_lock",
        "phase_gate",
        "open_blockers",
        "ci_status",
        "watchdog",
        "last_builder_result",
        "last_qa_result",
        "last_security_result",
        "last_eval_builder_result",
        "last_eval_result",
        "last_watchdog_verdict",
        "last_architect_decision",
    ]
    subset = {key: state.get(key) for key in keys if key in state}
    return json.dumps(subset, indent=2, sort_keys=True)


def build_prompt(parent_role: str, subagent: dict[str, Any], state: dict[str, Any]) -> str:
    return f"""You are {subagent.get('name', subagent.get('id'))}, a read-only specialist subagent.

Parent loop: {parent_role}
Mode: read-only
Focus: {subagent.get('focus', 'Specialist review')}

Rules:
- Do not edit production code, test files, docs, state, lock files, or git history.
- Do not advance roadmap phases, approve merges, change the write lock, or make final product decisions.
- Inspect only and report findings to the parent loop.
- If a production code change is required, report it as a required fix for Builder or the authorized parent loop.
- Use explicit verdict format so the control plane can normalize the result.

Required output:
Verdict: PASS, REQUEST_FIXES, PROCESS_WARNING, or STOP
Summary:
Files reviewed:
Tests/checks run:
Risks:
Required fixes:

Project state snapshot:
```json
{state_snapshot(state)}
```

Specialist assignment:
{subagent.get('prompt', '')}
"""


def run_subagent(prompt_path: Path, command: str, actor: str) -> tuple[int, str]:
    adapter_command = [
        "python3",
        str(ROOT / "bin" / "agent-adapter.py"),
        "--role",
        actor,
        "--prompt-file",
        str(prompt_path),
    ]
    if command:
        adapter_command.extend(["--command", command])
    result = subprocess.run(
        adapter_command,
        cwd=ROOT.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode, result.stdout


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def guard_snapshot(actor: str, enabled: bool) -> Path | None:
    if not enabled:
        return None
    result = run_command(["python3", str(ROOT / "bin" / "guard-files.py"), "snapshot", "--role", actor])
    if result.returncode != 0:
        raise SystemExit(f"Subagent file guard snapshot failed for {actor}:\n{result.stdout}")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return Path(lines[-1]) if lines else None


def guard_check(actor: str, snapshot: Path | None, enabled: bool, open_blocker: bool) -> bool:
    if not enabled or snapshot is None:
        return False
    command = [
        "python3",
        str(ROOT / "bin" / "guard-files.py"),
        "check",
        "--snapshot",
        str(snapshot),
        "--role",
        actor,
        "--mode",
        "read-only",
    ]
    if open_blocker:
        command.append("--open-blocker")
    result = run_command(command)
    if result.stdout:
        print(result.stdout, end="")
    log_event("File Guard", "subagent_check_completed", f"{actor} exit={result.returncode}")
    return result.returncode != 0


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def normalize_subagent_report(report_path: Path, open_blockers: bool) -> tuple[str, bool]:
    command = ["python3", str(ROOT / "bin" / "normalize-report.py"), "--role", "subagent"]
    if open_blockers:
        command.append("--open-blockers")
    command.append(str(report_path))
    result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Subagent report normalization failed:\n{result.stdout}")

    state = load_state()
    normalized_paths = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
    latest = normalized_paths[-1] if normalized_paths else None
    verdict = ""
    negative = False
    if latest:
        data = json.loads(latest.read_text())
        verdict = str(data.get("verdict") or "").upper()
        negative = verdict in NEGATIVE_VERDICTS
        rel = str(latest.relative_to(ROOT))
        if rel not in state.setdefault("subagent_findings", []):
            state["subagent_findings"].append(rel)
        save_state(state)
    return verdict, negative


def main() -> int:
    args = parse_args()
    manifest = load_manifest(Path(args.manifest))
    state = load_state()
    subagents = select_subagents(manifest, args.role, args.agent_id)
    if not subagents:
        print(f"No subagents selected for role {args.role}.")
        return 0

    prompt_dir = ROOT / "subagents" / "prompts"
    report_dir = ROOT / "reports" / "subagents"
    any_negative = False
    file_guard_violation = False
    created_reports: list[str] = []

    for subagent in subagents:
        subagent_id = str(subagent.get("id"))
        actor = f"subagent:{subagent_id}"
        prompt = build_prompt(args.role, subagent, state)
        stamp = compact_ts()
        prompt_path = prompt_dir / f"{stamp}-{args.role}-{subagent_id}.md"
        report_path = report_dir / f"{stamp}-{args.role}-{subagent_id}.md"
        write_text(prompt_path, prompt)
        snapshot = guard_snapshot(actor, not args.disable_file_guard)
        exit_code, output = run_subagent(prompt_path, args.agent_command, actor)
        report_text = (
            f"# subagent report\n\n"
            f"Parent role: {args.role}\n"
            f"Subagent id: {subagent_id}\n"
            f"Subagent name: {subagent.get('name', subagent_id)}\n"
            f"Exit code: {exit_code}\n\n"
            "```text\n"
            f"{output}"
            "\n```\n"
        )
        write_text(report_path, report_text)
        file_guard_negative = guard_check(
            actor,
            snapshot,
            not args.disable_file_guard,
            not args.no_file_guard_blocker,
        )
        verdict, negative = normalize_subagent_report(report_path, args.open_blockers)
        file_guard_violation = file_guard_violation or file_guard_negative
        any_negative = any_negative or negative or file_guard_negative or exit_code != 0
        created_reports.append(str(report_path.relative_to(ROOT)))
        log_event("Subagent", "completed", f"{subagent_id} parent={args.role} verdict={verdict or 'missing'} exit={exit_code}")

    state = load_state()
    state.setdefault("subagent_runs", []).append(
        {
            "id": f"subagent-run-{compact_ts()}",
            "parent_role": args.role,
            "created_at": now(),
            "reports": created_reports,
            "agent_command": bool(args.agent_command),
            "negative_findings": any_negative,
        }
    )
    save_state(state)

    for report in created_reports:
        print(ROOT / report)
    if file_guard_violation:
        return 1
    if any_negative and args.fail_on_negative:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
