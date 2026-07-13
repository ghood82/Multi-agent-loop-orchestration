"""Tests for the daemon's loop/cost budget guards."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from _helpers import load_source, read_state, run_bin

daemon = load_source("orchestration_daemon", "orchestration-daemon.py")


def _state(attempts: int | None = None) -> dict:
    state: dict = {"daemon": {}}
    if attempts is not None:
        state["daemon"]["remediation_attempts"] = attempts
    return state


# --- unit tests of the budget predicate ---


def test_cap_zero_means_unlimited():
    assert daemon.remediation_exhausted(_state(99), 0) is False


def test_exhausted_at_cap():
    assert daemon.remediation_exhausted(_state(2), 2) is True
    assert daemon.remediation_exhausted(_state(1), 2) is False


def test_attempts_tolerates_bad_values():
    assert daemon.remediation_attempts({"daemon": {"remediation_attempts": "nope"}}) == 0
    assert daemon.remediation_attempts({}) == 0


# --- end-to-end: an unresolvable blocker stops for a human instead of looping ---


def test_daemon_pauses_on_remediation_budget(harness_repo: Path):
    run_bin(
        harness_repo,
        "update-state.py",
        "add-blocker",
        "unresolvable blocker",
        "--severity",
        "high",
        "--owner",
        "test",
    )
    result = subprocess.run(
        [
            sys.executable,
            "orchestration/bin/orchestration-daemon.py",
            "--continuous",
            "--max-steps",
            "10",
            "--sleep-seconds",
            "0",
            "--remediate-open-blockers",
            "--max-remediation-attempts",
            "2",
        ],
        cwd=harness_repo,
        env={**os.environ, "AGENT_PROVIDER": "prompt-only"},
        text=True,
        capture_output=True,
        timeout=180,
    )
    # Paused (not a clean 10-step run) after exactly the 2 allowed remediations.
    assert result.returncode == 1, result.stdout + result.stderr
    assert "budget exhausted" in result.stdout
    daemon_state = read_state(harness_repo)["daemon"]
    assert daemon_state["status"] == "paused_budget"
    assert daemon_state["remediation_attempts"] == 2
