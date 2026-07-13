"""Shared helpers for the test suite.

Two testing strategies are used:

- Pure-function unit tests import a bin script by file path (the names are
  hyphenated, so a normal import will not work) and exercise its report/verdict
  builders directly. These are fast and hermetic.
- Integration tests install the harness into a temporary git repo and drive the
  scripts as subprocesses, asserting on exit codes and JSON output.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
BIN = PROJECT_ROOT / "assets" / "runtime-harness" / "orchestration" / "bin"
CREATE_HARNESS = SCRIPTS / "create_runtime_harness.py"


def load_source(module_name: str, filename: str) -> ModuleType:
    """Import a (possibly hyphen-named) bin script by file path."""
    # The scripts import sibling modules (e.g. orchestration_state); make the bin
    # dir importable, as it is when a script runs as `python3 bin/<script>.py`.
    if str(BIN) not in sys.path:
        sys.path.insert(0, str(BIN))
    path = BIN / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ns(**kwargs: Any) -> argparse.Namespace:
    """Build an argparse.Namespace for pure-function tests."""
    return argparse.Namespace(**kwargs)


def install_harness(repo: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    """Init a git repo and install the harness into it."""
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    args = {
        "--project-name": "Test Project",
        "--repo-name": "test-repo",
        "--current-phase": "Phase 1",
        "--current-objective": "Exercise the gates.",
        "--test-command": "pytest",
    }
    for key, value in overrides.items():
        args[f"--{key.replace('_', '-')}"] = value
    command = [sys.executable, str(CREATE_HARNESS), "--target", str(repo)]
    for flag, value in args.items():
        command.extend([flag, value])
    return subprocess.run(
        command, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True, timeout=120
    )


def run_bin(repo: Path, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run an installed bin script inside the harness repo."""
    return subprocess.run(
        [sys.executable, f"orchestration/bin/{script}", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        timeout=60,
    )


def read_state(repo: Path) -> dict[str, Any]:
    return json.loads((repo / "orchestration" / "state.json").read_text())


def write_state(repo: Path, state: dict[str, Any]) -> None:
    (repo / "orchestration" / "state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n"
    )
