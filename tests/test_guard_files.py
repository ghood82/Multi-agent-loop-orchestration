"""Unit tests for the file-guard classification helpers."""

from __future__ import annotations

from _helpers import load_source

guard = load_source("guard_files", "guard-files.py")


def test_matches_glob_and_dir_patterns():
    assert guard.matches("src/app.py", ["src/**"])
    assert guard.matches("src/app.py", ["src/"])  # trailing slash expands to /**
    assert guard.matches("a/b/c.py", ["**/c.py"]) or guard.matches("a/b/c.py", ["a/**"])
    assert not guard.matches("lib/app.py", ["src/**"])
    assert guard.matches("README.md", ["*.md"])


def test_role_mode_resolution():
    assert guard.role_mode("builder", "auto") == "write"
    assert guard.role_mode("remediation", "auto") == "write"
    assert guard.role_mode("docs", "auto") == "docs-only"
    assert guard.role_mode("qa", "auto") == "read-only"
    assert guard.role_mode("security:subagent", "auto") == "read-only"
    # explicit mode overrides auto resolution
    assert guard.role_mode("qa", "write") == "write"


def test_violations_read_only_role():
    v = guard.violations_for("qa", "read-only", ["src/app.py"], [], [])
    assert v and "read-only" in v[0]


def test_violations_docs_only_role():
    assert not guard.violations_for("docs", "docs-only", ["docs/x.md", "notes.md"], [], [])
    v = guard.violations_for("docs", "docs-only", ["src/app.py"], [], [])
    assert v and "docs" in v[0]


def test_violations_write_scope_and_forbidden():
    # in allowed scope: no violation
    assert not guard.violations_for("builder", "write", ["src/app.py"], ["src/**"], [])
    # outside allowed scope
    v = guard.violations_for("builder", "write", ["lib/x.py"], ["src/**"], [])
    assert v and "outside allowed scope" in v[0]
    # forbidden beats allowed
    v = guard.violations_for("builder", "write", ["src/secret.py"], ["src/**"], ["src/secret.py"])
    assert v and "forbidden" in v[0]


def test_changed_files_detects_additions_and_edits():
    before = {"a": "h1", "b": "h2"}
    after = {"a": "h1", "b": "CHANGED", "c": "new"}
    assert guard.changed_files(before, after) == ["b", "c"]
