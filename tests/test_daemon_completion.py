"""Tests for the daemon's verified-completion gate (--require-role-completion)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from _helpers import load_source, read_state

daemon = load_source("orchestration_daemon", "orchestration-daemon.py")

HEAD = "a" * 40
OTHER = "b" * 40


def _state(role: str, verdict: str = "", commit: str = "") -> dict:
    entry = {}
    if verdict:
        entry["verdict"] = verdict
    if commit:
        entry["commit"] = commit
    return {"role_verdicts": {role: entry}} if entry else {"role_verdicts": {}}


# --- unit tests of the completion predicate ---


def test_writer_completes_on_new_commit():
    # No verdict, but a commit was made (HEAD advanced).
    assert daemon.role_completed("builder", _state("builder"), OTHER, HEAD) is True


def test_writer_incomplete_without_commit_or_verdict():
    assert daemon.role_completed("builder", _state("builder"), HEAD, HEAD) is False


def test_writer_completes_on_fresh_verdict_without_commit():
    state = _state("builder", verdict="PASS", commit=HEAD)
    assert daemon.role_completed("builder", state, HEAD, HEAD) is True


def test_reviewer_completes_on_fresh_verdict():
    state = _state("qa", verdict="PASS", commit=HEAD)
    assert daemon.role_completed("qa", state, HEAD, HEAD) is True


def test_reviewer_incomplete_without_verdict():
    assert daemon.role_completed("qa", _state("qa"), HEAD, HEAD) is False


def test_reviewer_incomplete_on_stale_verdict():
    state = _state("qa", verdict="PASS", commit=OTHER)  # verdict bound to an older commit
    assert daemon.role_completed("qa", state, HEAD, HEAD) is False


def test_unknown_role_does_not_block():
    assert daemon.role_completed("mystery", {}, HEAD, HEAD) is True


# --- end-to-end ---


def _run_daemon(repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "orchestration/bin/orchestration-daemon.py", "--max-steps", "1", *extra],
        cwd=repo,
        env={**os.environ, "AGENT_PROVIDER": "prompt-only"},
        text=True,
        capture_output=True,
        timeout=120,
    )


def _commit(repo: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)


def test_require_completion_pauses_on_noop_builder(harness_repo: Path):
    _commit(harness_repo)  # HEAD exists so completion can be evaluated
    result = _run_daemon(harness_repo, "--require-role-completion")
    assert result.returncode == 1
    assert "no completion signal" in result.stdout
    assert read_state(harness_repo)["daemon"]["status"] == "paused_incomplete"


def test_default_still_advances_without_the_flag(harness_repo: Path):
    _commit(harness_repo)
    result = _run_daemon(harness_repo)  # no --require-role-completion
    assert result.returncode == 0
    daemon_state = read_state(harness_repo)["daemon"]
    assert daemon_state["status"] == "idle"
    assert daemon_state["cursor"] == 1  # advanced past builder
