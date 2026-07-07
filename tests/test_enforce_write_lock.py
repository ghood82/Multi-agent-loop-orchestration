"""Unit + integration tests for the production-code write-lock enforcer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _helpers import BIN, load_source

ewl = load_source("enforce_write_lock", "enforce-write-lock.py")
IGNORE = ewl.DEFAULT_IGNORES


def verdict(changed, state, require_active_lock=True, extra_forbidden=None):
    return ewl.evaluate(changed, state, IGNORE, require_active_lock, extra_forbidden or [])


def test_inactive_lock_blocks_production_change():
    v = verdict(["src/app.py"], {"write_lock": {"status": "inactive"}})
    assert not v["ok"]
    assert any("no active write lock" in item for item in v["violations"])


def test_docs_changes_are_never_blocked():
    v = verdict(
        ["README.md", "docs/guide.md", "memory/notes.md"], {"write_lock": {"status": "inactive"}}
    )
    assert v["ok"], v["violations"]


def test_orchestration_control_plane_is_ignored():
    v = verdict(["orchestration/state.json"], {"write_lock": {"status": "inactive"}})
    assert v["ok"], v["violations"]


def test_active_lock_allows_in_scope_change():
    state = {"write_lock": {"status": "active", "allowed_files": ["src/**"]}}
    assert verdict(["src/app.py"], state)["ok"]


def test_active_lock_blocks_out_of_scope_change():
    state = {"write_lock": {"status": "active", "allowed_files": ["src/**"]}}
    v = verdict(["lib/other.py"], state)
    assert not v["ok"]
    assert any("out of scope" in item for item in v["violations"])


def test_active_lock_with_empty_allowed_has_no_scope_restriction():
    state = {"write_lock": {"status": "active", "allowed_files": []}}
    assert verdict(["anywhere/x.py"], state)["ok"]


def test_forbidden_and_preserved_paths_always_block():
    state = {
        "write_lock": {"status": "active", "allowed_files": ["**"]},
        "preserved_components": ["docs/secret.md"],
        "forbidden_changes": ["**/auth.py"],
    }
    assert not verdict(["docs/secret.md"], state)["ok"]
    assert not verdict(["src/auth.py"], state)["ok"]


def test_ci_mode_allows_production_without_active_lock():
    # --no-require-active-lock: only forbidden/preserved + active scope enforced.
    v = verdict(["src/app.py"], {"write_lock": {"status": "inactive"}}, require_active_lock=False)
    assert v["ok"], v["violations"]


def test_ci_mode_still_blocks_forbidden():
    state = {"write_lock": {"status": "inactive"}, "forbidden_changes": ["**/auth.py"]}
    assert not verdict(["src/auth.py"], state, require_active_lock=False)["ok"]


def test_extra_forbidden_from_cli():
    state = {"write_lock": {"status": "active", "allowed_files": ["**"]}}
    assert not verdict(["src/app.py"], state, extra_forbidden=["src/app.py"])["ok"]


def test_missing_state_file_yields_empty_state():
    # load_state returns {} when the file is absent; evaluate treats that as no lock.
    v = verdict(["src/app.py"], {}, require_active_lock=False)
    assert v["ok"]


# --- git integration: the actual --staged / --against paths ---


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    orch = repo / "orchestration"
    orch.mkdir()
    (orch / "bin").mkdir()
    # Symlink-free copy of the enforcer so ROOT resolves to orchestration/.
    (orch / "bin" / "enforce-write-lock.py").write_text((BIN / "enforce-write-lock.py").read_text())


def _set_lock(repo: Path, status: str, allowed: list[str]) -> None:
    (repo / "orchestration" / "state.json").write_text(
        json.dumps({"write_lock": {"status": status, "owner": "Builder", "allowed_files": allowed}})
    )


def _run_staged(repo: Path):
    return subprocess.run(
        [sys.executable, "orchestration/bin/enforce-write-lock.py", "--staged", "--json"],
        cwd=repo,
        text=True,
        capture_output=True,
    )


def test_staged_integration_blocks_then_allows(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)

    # Inactive lock: staging production code is blocked (exit 1).
    _set_lock(repo, "inactive", [])
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('x')\n")
    _git(repo, "add", "src/app.py")
    result = _run_staged(repo)
    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False

    # Active, in-scope lock: allowed (exit 0).
    _set_lock(repo, "active", ["src/**"])
    result = _run_staged(repo)
    assert result.returncode == 0
    assert json.loads(result.stdout)["ok"] is True


def test_override_env_downgrades_to_warning(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    _set_lock(repo, "inactive", [])
    (repo / "app.py").write_text("x = 1\n")
    _git(repo, "add", "app.py")
    result = subprocess.run(
        [sys.executable, "orchestration/bin/enforce-write-lock.py", "--staged"],
        cwd=repo,
        text=True,
        capture_output=True,
        env={"ORCH_ALLOW_LOCK_OVERRIDE": "1", "PATH": __import__("os").environ["PATH"]},
    )
    assert result.returncode == 0
    assert "WARNING" in result.stdout + result.stderr
