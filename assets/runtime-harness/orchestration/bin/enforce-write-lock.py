#!/usr/bin/env python3
"""Enforce the production-code write lock at the git boundary.

This is the *enforcement* counterpart to ``guard-files.py``. Where the file
guard is an in-loop process-drift detector that records violations after a role
runs, this script fails the operation (a commit or a CI run) *before* an
unauthorized production-code change can land.

Core invariant: only one loop writes production code at a time. A change to a
production file is authorized only when the shared write lock in
``orchestration/state.json`` is ``active`` and the change stays inside the
lock's allowed scope. Changes to forbidden files, preserved components, or
declared forbidden changes are never authorized without human sign-off.

Sources of changes:

    --staged            staged changes (git diff --cached); used by the
                        installed pre-commit hook.
    --against REF       changes relative to a base ref (REF...HEAD merge-base);
                        used by the CI check on a pull request.
    --range A..B        an explicit commit range.
    --paths P [P ...]   an explicit list of paths (mainly for tests).

Docs, markdown, and the ``orchestration/`` control plane itself are never
treated as production code, so documentation loops and the harness stay
unblocked.

Emergency bypass: set ``ORCH_ALLOW_LOCK_OVERRIDE=1`` (or run
``git commit --no-verify``). The override is reported loudly so it shows up in
review.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"

# Kept in sync with guard-files.py so both tools classify files identically.
DEFAULT_IGNORES = [
    ".git/**",
    "orchestration/**",
]

DOCS_ALLOWED = [
    "*.md",
    "docs/**",
    "memory/**",
]

OVERRIDE_ENV = "ORCH_ALLOW_LOCK_OVERRIDE"
TRUTHY = {"1", "true", "yes", "on"}


def matches(path: str, patterns: list[str]) -> bool:
    normalized = path.replace(os.sep, "/")
    for pattern in patterns:
        pattern = pattern.strip().replace(os.sep, "/")
        if not pattern:
            continue
        if pattern.endswith("/"):
            pattern = f"{pattern}**"
        if fnmatch.fnmatch(normalized, pattern) or normalized == pattern:
            return True
        if pattern.endswith("/**") and normalized.startswith(pattern[:-3]):
            return True
    return False


def is_ignored(path: str, ignore: list[str]) -> bool:
    return matches(path, ignore)


def is_docs(path: str) -> bool:
    return matches(path, DOCS_ALLOWED)


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def git_names(diff_args: list[str]) -> list[str]:
    # Include Deleted (D) as well as Added/Copied/Modified/Renamed: deleting a
    # forbidden or preserved file is an unauthorized change too.
    result = run_git(["diff", "--name-only", "--diff-filter=ACMRD", "-z", *diff_args])
    if result.returncode != 0:
        raise SystemExit(f"git diff failed: {result.stdout.strip()}")
    return sorted({name for name in result.stdout.split("\0") if name})


def changed_paths(args: argparse.Namespace) -> list[str]:
    if args.paths:
        return sorted({p for p in args.paths if p})
    if args.staged:
        return git_names(["--cached"])
    if args.against:
        return git_names([f"{args.against}...HEAD"])
    if args.range:
        return git_names([args.range])
    raise SystemExit("Choose one source: --staged, --against, --range, or --paths.")


def load_state() -> dict[str, Any]:
    try:
        state = json.loads(STATE_FILE.read_text())
    except FileNotFoundError:
        # Missing state is handled explicitly in main(); treat as empty here.
        return {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON at {STATE_FILE}: {exc}") from exc
    return state if isinstance(state, dict) else {}


def as_patterns(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def evaluate(
    changed: list[str],
    state: dict[str, Any],
    ignore: list[str],
    require_active_lock: bool,
    extra_forbidden: list[str],
) -> dict[str, Any]:
    """Return a structured verdict for the given changed files.

    Pure function: no git, no filesystem, no state mutation. This is the unit
    tested by the smoke test.
    """
    lock = state.get("write_lock", {}) if isinstance(state.get("write_lock"), dict) else {}
    lock_active = str(lock.get("status", "inactive")).lower() == "active"
    allowed = as_patterns(lock.get("allowed_files"))
    forbidden = (
        as_patterns(lock.get("forbidden_files"))
        + as_patterns(state.get("forbidden_changes"))
        + as_patterns(state.get("preserved_components"))
        + [p for p in extra_forbidden if p.strip()]
    )

    considered = [p for p in changed if not is_ignored(p, ignore)]
    production = [p for p in considered if not is_docs(p)]

    violations: list[str] = []

    # Forbidden / preserved paths are off-limits for any change, docs included.
    for path in considered:
        if forbidden and matches(path, forbidden):
            violations.append(
                f"forbidden change: {path} matches a forbidden or preserved-component pattern"
            )

    if production:
        if require_active_lock and not lock_active:
            owner = lock.get("owner", "the authorized writer")
            violations.append(
                "no active write lock: production-code changes require an active lock held by "
                f"{owner} (activate it via the harness before editing production code)"
            )
        if lock_active and allowed:
            for path in production:
                if matches(path, forbidden):
                    continue  # already reported above
                if not matches(path, allowed):
                    violations.append(
                        f"out of scope: {path} is outside the active write lock's allowed_files"
                    )

    return {
        "lock_active": lock_active,
        "lock_owner": lock.get("owner"),
        "lock_scope": lock.get("scope"),
        "require_active_lock": require_active_lock,
        "changed_files": changed,
        "considered_files": considered,
        "production_files": production,
        "allowed_patterns": allowed,
        "forbidden_patterns": forbidden,
        "violations": violations,
        "ok": not violations,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--staged", action="store_true", help="Check staged changes (pre-commit).")
    source.add_argument(
        "--against", metavar="REF", help="Check changes relative to a base ref (REF...HEAD)."
    )
    source.add_argument("--range", metavar="A..B", help="Check an explicit commit range.")
    source.add_argument(
        "--paths", nargs="+", metavar="PATH", help="Check an explicit list of paths."
    )
    parser.add_argument(
        "--require-active-lock",
        dest="require_active_lock",
        action="store_true",
        default=None,
        help="Fail when production files change without an active lock. Default: on for --staged, off otherwise.",
    )
    parser.add_argument(
        "--no-require-active-lock",
        dest="require_active_lock",
        action="store_false",
        help="Only enforce forbidden/preserved paths and active-lock scope (recommended for CI on human PRs).",
    )
    parser.add_argument(
        "--ignore", action="append", default=[], help="Extra ignore glob (repeatable)."
    )
    parser.add_argument(
        "--forbidden", action="append", default=[], help="Extra forbidden glob (repeatable)."
    )
    parser.add_argument("--json", action="store_true", help="Emit the machine-readable verdict.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    require_active_lock = args.require_active_lock
    if require_active_lock is None:
        require_active_lock = bool(args.staged)

    # A missing state.json means the orchestration control plane is not installed
    # here (or is only partially installed). There is genuinely nothing to
    # enforce, so allow the operation rather than blocking every commit with a
    # confusing "no active write lock" message.
    if not STATE_FILE.exists():
        message = (
            f"No orchestration state.json at {STATE_FILE}; "
            "write-lock enforcement is inactive (control plane not installed)."
        )
        if args.json:
            print(json.dumps({"ok": True, "enforced": False, "reason": message}, sort_keys=True))
        else:
            print(message)
        return 0

    changed = changed_paths(args)
    state = load_state()
    ignore = DEFAULT_IGNORES + args.ignore
    verdict = evaluate(changed, state, ignore, require_active_lock, args.forbidden)

    override = os.environ.get(OVERRIDE_ENV, "").strip().lower() in TRUTHY
    verdict["override"] = override

    if args.json:
        print(json.dumps(verdict, indent=2, sort_keys=True))
    elif verdict["violations"]:
        print("Write-lock enforcement found unauthorized changes:", file=sys.stderr)
        for item in verdict["violations"]:
            print(f"  - {item}", file=sys.stderr)
        print(
            "\nAcquire/adjust the production-code write lock through the orchestration harness, "
            f"move the change into scope, or bypass in an emergency with {OVERRIDE_ENV}=1 "
            "(or `git commit --no-verify`).",
            file=sys.stderr,
        )
    else:
        print("Write-lock check passed.")

    if verdict["violations"] and not override:
        return 1
    if verdict["violations"] and override:
        print(
            f"WARNING: {OVERRIDE_ENV} set; allowing {len(verdict['violations'])} write-lock "
            "violation(s). This bypass should appear in review.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
