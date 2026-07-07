"""Tests for the write-lock lifecycle command and its integrations."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from _helpers import read_state, run_bin, write_state

BIN_REL = "orchestration/bin"


def _builder_env() -> dict:
    return {"AGENT_PROVIDER": "prompt-only", "PATH": os.environ["PATH"]}


def _lock_file(repo: Path) -> dict:
    return json.loads((repo / "orchestration" / "locks" / "production-code.lock").read_text())


def test_acquire_activates_and_syncs(harness_repo: Path):
    run_bin(harness_repo, "configure-project.py", "--allowed-file", "src/**")
    result = run_bin(harness_repo, "write-lock.py", "acquire", "--owner", "Builder", "--json")
    assert result.returncode == 0
    state_lock = read_state(harness_repo)["write_lock"]
    assert state_lock["status"] == "active"
    assert state_lock["owner"] == "Builder"
    assert "src/**" in state_lock["allowed_files"]
    # state.json and the lock-file mirror agree
    assert _lock_file(harness_repo)["status"] == "active"
    assert _lock_file(harness_repo)["allowed_files"] == state_lock["allowed_files"]


def test_enforcer_sees_lock_after_acquire(harness_repo: Path):
    run_bin(harness_repo, "configure-project.py", "--allowed-file", "src/**")
    run_bin(harness_repo, "write-lock.py", "acquire")
    ok = run_bin(
        harness_repo,
        "enforce-write-lock.py",
        "--paths",
        "src/app.py",
        "--require-active-lock",
        "--json",
    )
    assert json.loads(ok.stdout)["ok"] is True
    blocked = run_bin(
        harness_repo,
        "enforce-write-lock.py",
        "--paths",
        "lib/x.py",
        "--require-active-lock",
        "--json",
    )
    assert json.loads(blocked.stdout)["ok"] is False


def test_cannot_steal_without_force(harness_repo: Path):
    run_bin(harness_repo, "write-lock.py", "acquire", "--owner", "Builder")
    steal = run_bin(harness_repo, "write-lock.py", "acquire", "--owner", "QA")
    assert steal.returncode == 2
    assert read_state(harness_repo)["write_lock"]["owner"] == "Builder"
    forced = run_bin(harness_repo, "write-lock.py", "acquire", "--owner", "QA", "--force")
    assert forced.returncode == 0
    assert read_state(harness_repo)["write_lock"]["owner"] == "QA"


def test_release_deactivates_and_syncs(harness_repo: Path):
    run_bin(harness_repo, "write-lock.py", "acquire")
    run_bin(harness_repo, "write-lock.py", "release")
    assert read_state(harness_repo)["write_lock"]["status"] == "inactive"
    assert _lock_file(harness_repo)["status"] == "inactive"
    status = run_bin(harness_repo, "write-lock.py", "status", "--json")
    assert json.loads(status.stdout)["mirror_out_of_sync"] is False


def test_status_detects_drift(harness_repo: Path):
    # Desync the state's write_lock without touching the lock-file mirror.
    state = read_state(harness_repo)
    state["write_lock"] = {"status": "active", "owner": "Builder", "allowed_files": ["src/**"]}
    write_state(harness_repo, state)
    status = run_bin(harness_repo, "write-lock.py", "status", "--json")
    assert json.loads(status.stdout)["mirror_out_of_sync"] is True


def test_configure_project_mirrors_lock_file(harness_repo: Path):
    run_bin(harness_repo, "configure-project.py", "--allowed-file", "src/**")
    status = run_bin(harness_repo, "write-lock.py", "status", "--json")
    assert json.loads(status.stdout)["mirror_out_of_sync"] is False


def test_run_builder_auto_acquires(harness_repo: Path):
    run_bin(harness_repo, "configure-project.py", "--allowed-file", "src/**")
    result = subprocess.run(
        ["bash", f"{BIN_REL}/run-builder.sh"],
        cwd=harness_repo,
        env=_builder_env(),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lock = read_state(harness_repo)["write_lock"]
    assert lock["status"] == "active"
    assert lock["owner"] == "Builder"
    assert "src/**" in lock["allowed_files"]


def test_run_builder_stops_when_held_by_other(harness_repo: Path):
    run_bin(harness_repo, "write-lock.py", "acquire", "--owner", "QA")
    result = subprocess.run(
        ["bash", f"{BIN_REL}/run-builder.sh"],
        cwd=harness_repo,
        env=_builder_env(),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "write lock is active for QA" in (result.stdout + result.stderr)
