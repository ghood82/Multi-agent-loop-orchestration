"""Integration tests for the git hook installer."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _helpers import BIN

INSTALLER = BIN / "install-hooks.py"
HOOK_SOURCE = BIN.parent / "hooks" / "pre-commit"
MARKER = "orchestration: production-code write-lock enforcement"


def _init_repo_with_bin(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    orch_bin = repo / "orchestration" / "bin"
    orch_bin.mkdir(parents=True)
    (orch_bin / "install-hooks.py").write_text(INSTALLER.read_text())
    hooks = repo / "orchestration" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-commit").write_text(HOOK_SOURCE.read_text())
    return repo


def _install(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "orchestration/bin/install-hooks.py", "--target", str(repo), *args],
        cwd=repo,
        text=True,
        capture_output=True,
    )


def test_install_creates_managed_hook(tmp_path: Path):
    repo = _init_repo_with_bin(tmp_path)
    result = _install(repo)
    assert result.returncode == 0
    hook = repo / ".git" / "hooks" / "pre-commit"
    assert hook.exists()
    assert MARKER in hook.read_text()


def test_check_reports_installed_state(tmp_path: Path):
    repo = _init_repo_with_bin(tmp_path)
    # not installed yet
    assert _install(repo, "--check").returncode == 1
    _install(repo)
    assert _install(repo, "--check").returncode == 0


def test_preserves_existing_hook_and_chains(tmp_path: Path):
    repo = _init_repo_with_bin(tmp_path)
    existing = repo / ".git" / "hooks" / "pre-commit"
    existing.write_text("#!/bin/sh\necho custom\n")
    _install(repo)
    hooks_dir = repo / ".git" / "hooks"
    assert (hooks_dir / "pre-commit.local").exists()
    assert "echo custom" in (hooks_dir / "pre-commit.local").read_text()
    assert MARKER in (hooks_dir / "pre-commit").read_text()


def test_idempotent_no_backup_stacking(tmp_path: Path):
    repo = _init_repo_with_bin(tmp_path)
    _install(repo)
    _install(repo)  # second run should not create a backup of our own hook
    assert not (repo / ".git" / "hooks" / "pre-commit.local").exists()


def test_refreshes_backup_when_hook_recustomized(tmp_path: Path):
    repo = _init_repo_with_bin(tmp_path)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho v1\n")
    _install(repo)  # backs up v1, installs the managed hook
    # User re-customizes the pre-commit hook after the first install.
    hook.write_text("#!/bin/sh\necho v2\n")
    _install(repo)  # should refresh the backup to the newer customization
    assert "echo v2" in (repo / ".git" / "hooks" / "pre-commit.local").read_text()
