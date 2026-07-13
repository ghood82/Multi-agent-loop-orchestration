"""Tests for concurrency-safe state access (atomic writes + advisory lock)."""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

from _helpers import load_source, read_state

ostate = load_source("orchestration_state", "orchestration_state.py")


# --- unit tests of the primitives ---


def test_write_atomic_roundtrip(tmp_path: Path):
    path = tmp_path / "state.json"
    ostate.write_atomic(path, {"a": 1, "b": [2, 3]})
    assert json.loads(path.read_text()) == {"a": 1, "b": [2, 3]}
    # No temp files left behind.
    assert not list(tmp_path.glob(".state.*.tmp"))


def test_begin_commit_roundtrip(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text('{"x": 1}')
    state = ostate.begin(path)
    state["x"] = 2
    ostate.commit(path, state)
    assert json.loads(path.read_text())["x"] == 2


def test_begin_is_reentrant(tmp_path: Path):
    # A script may load state more than once without self-deadlocking.
    path = tmp_path / "state.json"
    path.write_text('{"n": 0}')
    ostate.begin(path)
    inner = ostate.begin(path)
    inner["n"] = 5
    ostate.commit(path, inner)
    ostate.commit(path, inner)
    assert json.loads(path.read_text())["n"] == 5


# --- end-to-end: concurrent writers must not lose updates ---


def test_concurrent_add_blocker_no_lost_updates(harness_repo: Path):
    n = 20

    def add(i: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "orchestration/bin/update-state.py",
                "add-blocker",
                f"race-blocker-{i}",
                "--severity",
                "low",
                "--owner",
                "test",
            ],
            cwd=harness_repo,
            text=True,
            capture_output=True,
            timeout=60,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(add, range(n)))

    assert all(r.returncode == 0 for r in results), [r.stderr for r in results if r.returncode]

    descriptions = {b.get("description") for b in read_state(harness_repo).get("open_blockers", [])}
    missing = [i for i in range(n) if f"race-blocker-{i}" not in descriptions]
    assert not missing, f"lost updates under concurrency: {missing}"
