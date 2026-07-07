#!/usr/bin/env python3
"""Install the orchestration git hooks into a target repository.

This wires the write-lock enforcement (``enforce-write-lock.py``) into git so
an unauthorized production-code change fails at commit time rather than only
being recorded after the fact.

Behaviour:

- Resolves the repo's hooks directory (worktree-aware, via ``git rev-parse``).
- Installs ``orchestration/hooks/pre-commit`` as ``.git/hooks/pre-commit``.
- Preserves any pre-existing, non-orchestration pre-commit hook as
  ``pre-commit.local``; the installed hook chains to it so existing behaviour
  keeps working.
- Is idempotent: re-running refreshes the managed hook without stacking backups.

Use ``--check`` to verify installation without writing anything (exit non-zero
if the hook is missing or stale).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK_SOURCE = ROOT / "hooks" / "pre-commit"
MARKER = "orchestration: production-code write-lock enforcement"


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def git_common_dir(cwd: Path) -> Path:
    result = run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd)
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    # Older git without --path-format: fall back to --git-dir.
    result = run_git(["rev-parse", "--git-dir"], cwd)
    if result.returncode != 0:
        raise SystemExit("install-hooks requires a git repository.")
    git_dir = Path(result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (cwd / git_dir).resolve()
    return git_dir


def hooks_dir(cwd: Path) -> Path:
    # Honour a configured core.hooksPath so we do not silently install a hook
    # git will never run.
    configured = run_git(["config", "--get", "core.hooksPath"], cwd)
    if configured.returncode == 0 and configured.stdout.strip():
        path = Path(configured.stdout.strip())
        if not path.is_absolute():
            path = (cwd / path).resolve()
        return path
    return git_common_dir(cwd) / "hooks"


def is_managed(text: str) -> bool:
    return MARKER in text


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--target", default=".", help="Repository root. Defaults to current directory."
    )
    parser.add_argument(
        "--check", action="store_true", help="Verify the hook is installed; write nothing."
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable result.")
    return parser.parse_args(argv)


def emit(result: dict, as_json: bool) -> None:
    if as_json:
        import json

        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["message"])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target = Path(args.target).resolve()

    if not HOOK_SOURCE.exists():
        raise SystemExit(f"Hook source not found: {HOOK_SOURCE}")

    hooks = hooks_dir(target)
    hook_path = hooks / "pre-commit"

    if args.check:
        installed = hook_path.exists() and is_managed(hook_path.read_text())
        result = {
            "installed": installed,
            "hook_path": str(hook_path),
            "message": "Write-lock hook installed."
            if installed
            else "Write-lock hook is NOT installed.",
        }
        emit(result, args.json)
        return 0 if installed else 1

    hooks.mkdir(parents=True, exist_ok=True)
    source_text = HOOK_SOURCE.read_text()
    preserved = None

    if hook_path.exists():
        existing = hook_path.read_text()
        if not is_managed(existing):
            local = hooks / "pre-commit.local"
            if not local.exists():
                local.write_text(existing)
                local.chmod(0o755)
                preserved = str(local)

    hook_path.write_text(source_text)
    hook_path.chmod(0o755)

    message = f"Installed write-lock pre-commit hook at {hook_path}."
    if preserved:
        message += f" Preserved existing hook as {preserved} (it still runs after the check)."
    emit(
        {
            "installed": True,
            "hook_path": str(hook_path),
            "preserved": preserved,
            "message": message,
        },
        args.json,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
