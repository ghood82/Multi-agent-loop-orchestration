"""End-to-end tests that drive the installed gate scripts as subprocesses.

These prove the CLI wiring, exit codes, and JSON output of the real installed
harness, complementing the pure-function unit tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from _helpers import run_bin


def test_decision_gate_high_risk_requires_human(harness_repo: Path):
    result = run_bin(
        harness_repo,
        "decision-gate.py",
        "--risk",
        "high",
        "--decision",
        "Change auth",
        "--evidence",
        "reports/json/x.json",
        "--json",
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["decision"] == "HUMAN_REQUIRED"


def test_decision_gate_low_risk_autonomous(harness_repo: Path):
    result = run_bin(
        harness_repo,
        "decision-gate.py",
        "--risk",
        "low",
        "--decision",
        "Rerun tests",
        "--evidence",
        "reports/json/x.json",
        "--json",
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "APPROVED_AUTONOMOUS"


def test_phase_gate_fresh_state_stops(harness_repo: Path):
    result = run_bin(harness_repo, "phase-gate.py", "--json", "--strict")
    assert result.returncode == 1
    assert json.loads(result.stdout)["verdict"] == "STOP"


def test_enforce_write_lock_installed_cli(harness_repo: Path):
    # Template state ships an inactive lock.
    blocked = run_bin(
        harness_repo,
        "enforce-write-lock.py",
        "--paths",
        "src/app.py",
        "--require-active-lock",
        "--json",
    )
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["ok"] is False

    allowed = run_bin(
        harness_repo,
        "enforce-write-lock.py",
        "--paths",
        "src/app.py",
        "--no-require-active-lock",
        "--json",
    )
    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["ok"] is True


def test_hook_installed_by_default(harness_repo: Path):
    # create_runtime_harness installs the hook automatically in a git repo.
    assert (harness_repo / ".git" / "hooks" / "pre-commit").exists()
    result = run_bin(harness_repo, "install-hooks.py", "--check")
    assert result.returncode == 0


def test_health_check_runs_and_emits_json(harness_repo: Path):
    # health-check emits JSON by default (--summary switches to text).
    result = run_bin(harness_repo, "health-check.py")
    assert result.returncode in {0, 1}
    payload = json.loads(result.stdout)
    assert "status" in payload or "failures" in payload
