"""Pytest fixtures for the orchestration test suite."""

from __future__ import annotations

from pathlib import Path

import pytest
from _helpers import install_harness


@pytest.fixture
def harness_repo(tmp_path: Path) -> Path:
    """A fresh git repo with the harness installed, isolated per test."""
    repo = tmp_path / "repo"
    repo.mkdir()
    install_harness(repo)
    return repo
