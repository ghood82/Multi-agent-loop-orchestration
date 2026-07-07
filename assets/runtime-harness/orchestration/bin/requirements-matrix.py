#!/usr/bin/env python3
"""Audit explicit orchestration requirements against runtime evidence."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"


Check = Callable[[dict[str, Any]], tuple[bool, str]]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def load_state() -> dict[str, Any]:
    state = load_json(STATE_FILE, {})
    if not isinstance(state, dict):
        raise SystemExit("state.json must contain an object.")
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": "requirements-matrix", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def rel(path: str) -> Path:
    return ROOT / path


def doc_text() -> str:
    parts = []
    for path in [ROOT / "README.md", ROOT / "tasks.md"]:
        if path.exists():
            parts.append(path.read_text())
    return "\n".join(parts).lower()


def file_check(path: str) -> Check:
    return lambda _state: ((ROOT / path).is_file(), path)


def dir_check(path: str) -> Check:
    return lambda _state: ((ROOT / path).is_dir(), path)


def executable_check(path: str) -> Check:
    return lambda _state: ((ROOT / path).is_file() and os.access(ROOT / path, os.X_OK), path)


def state_key_check(key: str) -> Check:
    return lambda state: (key in state, f"state.{key}")


def doc_phrase_check(phrase: str) -> Check:
    return lambda _state: (phrase.lower() in doc_text(), f"docs contain: {phrase}")


def daemon_roles_check(expected: list[str]) -> Check:
    def check(state: dict[str, Any]) -> tuple[bool, str]:
        daemon = state.get("daemon") if isinstance(state.get("daemon"), dict) else {}
        queue = daemon.get("queue") if isinstance(daemon.get("queue"), list) else []
        missing = [role for role in expected if role not in queue]
        return not missing, f"daemon.queue missing: {', '.join(missing) if missing else 'none'}"

    return check


def provider_check(expected: list[str]) -> Check:
    def check(_state: dict[str, Any]) -> tuple[bool, str]:
        config = load_json(ROOT / "agent-adapter.json", {})
        providers = config.get("providers") if isinstance(config, dict) else {}
        missing = [
            name for name in expected if not isinstance(providers, dict) or name not in providers
        ]
        return not missing, f"agent providers missing: {', '.join(missing) if missing else 'none'}"

    return check


def stop_reasons_check(expected: list[str]) -> Check:
    def check(state: dict[str, Any]) -> tuple[bool, str]:
        policy = (
            state.get("blocking_policy") if isinstance(state.get("blocking_policy"), dict) else {}
        )
        reasons = (
            policy.get("stop_immediately_for")
            if isinstance(policy.get("stop_immediately_for"), list)
            else []
        )
        missing = [reason for reason in expected if reason not in reasons]
        return not missing, f"stop reasons missing: {', '.join(missing) if missing else 'none'}"

    return check


def write_lock_check(state: dict[str, Any]) -> tuple[bool, str]:
    lock = state.get("write_lock") if isinstance(state.get("write_lock"), dict) else {}
    ok = (
        str(lock.get("owner", "")).lower() == "builder"
        and "allowed_files" in lock
        and "forbidden_files" in lock
    )
    return ok, "write_lock.owner=Builder with allowed_files and forbidden_files"


def human_gate_check(state: dict[str, Any]) -> tuple[bool, str]:
    return (
        "human_approval_required" in state and "approval_requests" in state,
        "human_approval_required and approval_requests",
    )


def eval_tooling_check(state: dict[str, Any]) -> tuple[bool, str]:
    paths = [
        ROOT / "bin" / "eval-fixture.py",
        ROOT / "bin" / "eval-result.py",
        ROOT / "bin" / "prepare-watchdog-evidence.py",
        ROOT / "evals" / "fixtures",
        ROOT / "evals" / "results",
        ROOT / "evals" / "rubrics" / "project-quality-rubric.md",
    ]
    keys = [
        "eval_fixtures",
        "eval_results",
        "last_eval_result_artifact",
        "watchdog_evidence",
        "quality_rubrics",
    ]
    ok = all(path.exists() for path in paths) and all(key in state for key in keys)
    return ok, "eval fixture/result scripts, Watchdog evidence prep, rubric, dirs, and state keys"


def decision_policy_check(state: dict[str, Any]) -> tuple[bool, str]:
    policy = state.get("decision_policy") if isinstance(state.get("decision_policy"), dict) else {}
    ok = (
        all(key in policy for key in ["low_risk", "medium_risk", "high_risk"])
        and (ROOT / "bin" / "decision-gate.py").is_file()
    )
    return ok, "decision_policy low/medium/high buckets and decision-gate.py"


REQUIREMENTS: list[dict[str, Any]] = [
    {
        "id": "skill-runtime-harness",
        "requirement": "Reusable project-local orchestration harness exists.",
        "checks": [
            file_check("state.json"),
            file_check("README.md"),
            dir_check("bin"),
            file_check("operating-policy.json"),
        ],
    },
    {
        "id": "shared-state-template",
        "requirement": "Shared project state includes roadmap, phase, branch, PR, allowed/forbidden files, preserved components, risks, blockers, loop results, next action, and human approval.",
        "checks": [
            state_key_check("project_name"),
            state_key_check("repo"),
            state_key_check("roadmap"),
            state_key_check("current_phase"),
            state_key_check("current_objective"),
            state_key_check("active_branch"),
            state_key_check("active_pr"),
            state_key_check("preserved_components"),
            state_key_check("forbidden_changes"),
            state_key_check("known_risks"),
            state_key_check("open_blockers"),
            state_key_check("last_builder_result"),
            state_key_check("last_qa_result"),
            state_key_check("last_security_result"),
            state_key_check("last_eval_result"),
            state_key_check("last_architect_decision"),
            state_key_check("last_documentation_update"),
            state_key_check("next_authorized_action"),
            state_key_check("human_approval_required"),
        ],
    },
    {
        "id": "single-writer",
        "requirement": "Only one loop writes production code at a time; Builder owns production-code edits by default.",
        "checks": [
            write_lock_check,
            file_check("locks/production-code.lock"),
            doc_phrase_check("only one loop writes production code at a time"),
        ],
    },
    {
        "id": "loop-prompts",
        "requirement": "Builder, QA, Security, Eval Builder, Eval, Watchdog, Architect, Documentation, and Remediation runners exist.",
        "checks": [
            executable_check("bin/run-builder.sh"),
            executable_check("bin/run-qa.sh"),
            executable_check("bin/run-security.sh"),
            executable_check("bin/run-eval-builder.sh"),
            executable_check("bin/run-eval.sh"),
            executable_check("bin/run-watchdog.sh"),
            executable_check("bin/run-architect.sh"),
            executable_check("bin/run-docs.sh"),
            executable_check("bin/run-remediation.sh"),
        ],
    },
    {
        "id": "handoff-sequence",
        "requirement": "Recommended handoff sequence is encoded.",
        "checks": [
            daemon_roles_check(
                [
                    "builder",
                    "qa",
                    "security",
                    "eval-builder",
                    "eval",
                    "watchdog",
                    "architect",
                    "docs",
                ]
            ),
            file_check("bin/handoff-packet.py"),
        ],
    },
    {
        "id": "human-product-owner-gate",
        "requirement": "Human Product Owner gate exists for high-impact decisions.",
        "checks": [
            human_gate_check,
            file_check("bin/approval-request.py"),
            doc_phrase_check("Human Product Owner"),
        ],
    },
    {
        "id": "stop-conditions",
        "requirement": "Global stop conditions and stop report format exist.",
        "checks": [
            stop_reasons_check(
                [
                    "security/privacy risk",
                    "schema migration",
                    "auth changes",
                    "external model behavior",
                    "preserved-component removal",
                    "API compatibility risk",
                    "product judgment",
                    "repeated test failures",
                    "process drift",
                    "unclear requirements",
                ]
            ),
            file_check("bin/stop-report.py"),
        ],
    },
    {
        "id": "blocker-recovery",
        "requirement": "Open blockers are enforced and can be remediated.",
        "checks": [
            state_key_check("blocking_policy"),
            file_check("bin/resume-plan.py"),
            file_check("bin/run-remediation.sh"),
            file_check("bin/update-state.py"),
        ],
    },
    {
        "id": "watchdog",
        "requirement": "Watchdog / Quality Governor loop exists and checks process/product/eval quality.",
        "checks": [
            state_key_check("watchdog"),
            executable_check("bin/run-watchdog.sh"),
            doc_phrase_check("Watchdog checks product quality"),
        ],
    },
    {
        "id": "eval-regression",
        "requirement": "Eval Builder and Eval Monitor can create fixtures, record expected-vs-actual results, and detect drift.",
        "checks": [eval_tooling_check, doc_phrase_check("expected vs actual")],
    },
    {
        "id": "security-privacy",
        "requirement": "Security / Privacy review loop exists and high-risk areas are represented.",
        "checks": [
            executable_check("bin/run-security.sh"),
            state_key_check("high_risk_areas"),
            doc_phrase_check("Security/Privacy"),
        ],
    },
    {
        "id": "phase-release-gates",
        "requirement": "Architect/release/phase gates prevent unsafe advancement.",
        "checks": [
            file_check("bin/phase-gate.py"),
            file_check("bin/release-gate.py"),
            state_key_check("phase_gate"),
            state_key_check("release_gate"),
        ],
    },
    {
        "id": "provider-adapter",
        "requirement": "Provider-neutral agent adapter and named presets exist.",
        "checks": [
            file_check("bin/agent-adapter.py"),
            file_check("bin/configure-agent-provider.py"),
            provider_check(
                [
                    "auto",
                    "prompt-only",
                    "command",
                    "codex-cli",
                    "claude-code",
                    "codex-subagent",
                    "custom-command",
                ]
            ),
        ],
    },
    {
        "id": "risk-decision-policy",
        "requirement": "Low/medium/high decision buckets route autonomous, research-first, and human-required decisions.",
        "checks": [decision_policy_check],
    },
    {
        "id": "subagents",
        "requirement": "Read-only subagent dispatch exists.",
        "checks": [
            file_check("bin/dispatch-subagents.py"),
            file_check("subagents/manifest.json"),
            state_key_check("subagent_runs"),
        ],
    },
    {
        "id": "one-command-adoption",
        "requirement": "One-command adoption path exists in the skill package and runtime has first setup intake.",
        "checks": [
            file_check("bin/setup-intake.py"),
            state_key_check("setup_intake"),
            doc_phrase_check("one-command"),
        ],
    },
    {
        "id": "operator-doctor",
        "requirement": "Operator doctor explains readiness and next exact command.",
        "checks": [
            file_check("bin/doctor.py"),
            state_key_check("doctor"),
            doc_phrase_check("doctor"),
        ],
    },
    {
        "id": "ops-check",
        "requirement": "Consolidated readiness check exists.",
        "checks": [
            file_check("bin/ops-check.py"),
            state_key_check("ops_check"),
            doc_phrase_check("consolidated"),
        ],
    },
    {
        "id": "docs-memory",
        "requirement": "Documentation / Memory Keeper updates shared state and project memory.",
        "checks": [
            executable_check("bin/run-docs.sh"),
            file_check("bin/sync-state-doc.py"),
            state_key_check("state_doc"),
        ],
    },
    {
        "id": "acceptance-audit",
        "requirement": "Acceptance and requirement audits can verify the operating system.",
        "checks": [
            file_check("bin/acceptance-audit.py"),
            file_check("bin/requirements-matrix.py"),
            state_key_check("acceptance_audit"),
        ],
    },
]


def run_requirement(requirement: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    evidence = []
    missing = []
    for check in requirement["checks"]:
        passed, detail = check(state)
        evidence.append({"passed": passed, "detail": detail})
        if not passed:
            missing.append(detail)
    status = "PASS" if not missing else "FAIL"
    return {
        "id": requirement["id"],
        "requirement": requirement["requirement"],
        "status": status,
        "evidence": evidence,
        "missing": missing,
    }


def build_report() -> dict[str, Any]:
    state = load_state()
    rows = [run_requirement(requirement, state) for requirement in REQUIREMENTS]
    failures = [row for row in rows if row["status"] != "PASS"]
    verdict = "PASS" if not failures else "FAIL"
    return {
        "id": f"{compact_ts()}-requirements-matrix",
        "role": "requirements-matrix",
        "status": "completed",
        "verdict": verdict,
        "summary": "Requirement matrix passed."
        if verdict == "PASS"
        else f"{len(failures)} requirement(s) missing evidence.",
        "created_at": now(),
        "requirements_total": len(rows),
        "requirements_passed": len(rows) - len(failures),
        "requirements_failed": len(failures),
        "rows": rows,
        "failures": failures,
    }


def write_report(report: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports" / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    state = load_state()
    rel_path = str(path.relative_to(ROOT))
    state.setdefault("structured_reports", []).append(rel_path)
    state["requirements_matrix"] = {
        "last_decision": report["verdict"],
        "last_checked_at": report["created_at"],
        "last_report": rel_path,
        "requirements_total": report["requirements_total"],
        "requirements_passed": report["requirements_passed"],
        "requirements_failed": report["requirements_failed"],
    }
    save_state(state)
    log_event(report["verdict"], rel_path)
    return path


def print_text(report: dict[str, Any], report_path: Path | None) -> None:
    print("# Requirements Matrix")
    print(f"Verdict: {report['verdict']}")
    print(f"Passed: {report['requirements_passed']}/{report['requirements_total']}")
    if report_path:
        print(f"Report: {report_path}")
    if report["failures"]:
        print()
        print("## Missing Evidence")
        for row in report["failures"]:
            print(f"- {row['id']}: {', '.join(row['missing'])}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict", action="store_true", help="Return nonzero unless every requirement passes."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report()
    report_path = write_report(report) if args.write_report else None
    if args.json:
        output = dict(report)
        if report_path:
            output["report_path"] = str(report_path)
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print_text(report, report_path)
    return 1 if args.strict and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
