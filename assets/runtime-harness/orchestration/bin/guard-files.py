#!/usr/bin/env python3
"""Guard repo file changes by role and write-lock policy."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"
GUARD_DIR = ROOT / "guards"

DEFAULT_IGNORES = [
    ".git/**",
    "orchestration/**",
]

DOCS_ALLOWED = [
    "*.md",
    "docs/**",
    "memory/**",
]

WRITE_ROLES = {"builder", "remediation"}
DOCS_ROLES = {"docs"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def run(command: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def git_root() -> Path:
    result = run(["git", "rev-parse", "--show-toplevel"], ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit("File guard requires a git repository.")
    return Path(result.stdout.strip()).resolve()


def git_files(repo: Path) -> list[str]:
    tracked = run(["git", "ls-files", "-z"], repo).stdout.split("\0")
    untracked = run(["git", "ls-files", "-o", "--exclude-standard", "-z"], repo).stdout.split("\0")
    return sorted({path for path in tracked + untracked if path})


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON: {exc}") from exc


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(role: str, event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": role, "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


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


def file_fingerprint(repo: Path, rel_path: str) -> str:
    path = repo / rel_path
    if not path.exists():
        return "MISSING"
    if path.is_dir():
        return "DIR"
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    mode = path.stat().st_mode & 0o777
    return f"{mode:o}:{hasher.hexdigest()}"


def snapshot_state(repo: Path, ignore: list[str]) -> dict[str, str]:
    files = {}
    for rel_path in git_files(repo):
        if matches(rel_path, ignore):
            continue
        files[rel_path] = file_fingerprint(repo, rel_path)
    return files


def role_mode(role: str, requested: str) -> str:
    if requested != "auto":
        return requested
    base_role = role.split(":", 1)[0].lower()
    if base_role in WRITE_ROLES:
        return "write"
    if base_role in DOCS_ROLES:
        return "docs-only"
    return "read-only"


def state_patterns(state: dict[str, Any], key: str) -> list[str]:
    patterns: list[str] = []
    root_value = state.get(key, [])
    if isinstance(root_value, list):
        patterns.extend(str(item) for item in root_value)
    lock_value = state.get("write_lock", {}).get(key, [])
    if isinstance(lock_value, list):
        patterns.extend(str(item) for item in lock_value)
    return patterns


def add_blocker(state: dict[str, Any], role: str, description: str, evidence: str) -> None:
    blocker = {
        "id": f"blocker-{compact_ts()}",
        "status": "open",
        "severity": "high",
        "owner": role,
        "description": description,
        "created_at": now(),
        "evidence": evidence,
    }
    state.setdefault("open_blockers", []).append(blocker)


def record_guard_check(state: dict[str, Any], check: dict[str, Any]) -> None:
    state.setdefault("file_guard_checks", []).append(check)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--role", required=True)
    snapshot.add_argument(
        "--mode", default="auto", choices=["auto", "read-only", "write", "docs-only"]
    )
    snapshot.add_argument("--ignore", action="append", default=[])

    check = sub.add_parser("check")
    check.add_argument("--snapshot", required=True)
    check.add_argument("--role", required=True)
    check.add_argument(
        "--mode", default="auto", choices=["auto", "read-only", "write", "docs-only"]
    )
    check.add_argument("--allowed", action="append", default=[])
    check.add_argument("--forbidden", action="append", default=[])
    check.add_argument("--ignore", action="append", default=[])
    check.add_argument("--open-blocker", action="store_true")

    return parser.parse_args()


def cmd_snapshot(args: argparse.Namespace) -> int:
    repo = git_root()
    ignore = DEFAULT_IGNORES + args.ignore
    GUARD_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "id": f"guard-{compact_ts()}-{args.role}",
        "created_at": now(),
        "role": args.role,
        "mode": role_mode(args.role, args.mode),
        "repo": str(repo),
        "ignore": ignore,
        "files": snapshot_state(repo, ignore),
    }
    path = GUARD_DIR / f"{snapshot['id']}.json"
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    log_event("File Guard", "snapshot", f"{args.role} {path.relative_to(ROOT)}")
    print(path)
    return 0


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    paths = sorted(set(before) | set(after))
    return [path for path in paths if before.get(path) != after.get(path)]


def violations_for(
    role: str,
    mode: str,
    changed: list[str],
    allowed: list[str],
    forbidden: list[str],
) -> list[str]:
    violations: list[str] = []
    for path in changed:
        if mode == "read-only":
            violations.append(f"{role} is read-only but changed {path}")
            continue
        if mode == "docs-only" and not matches(path, DOCS_ALLOWED):
            violations.append(
                f"{role} may only change docs/memory/markdown files but changed {path}"
            )
            continue
        if forbidden and matches(path, forbidden):
            violations.append(f"{role} changed forbidden file {path}")
            continue
        if mode == "write" and allowed and not matches(path, allowed):
            violations.append(f"{role} changed file outside allowed scope: {path}")
    return violations


def cmd_check(args: argparse.Namespace) -> int:
    repo = git_root()
    snapshot_path = Path(args.snapshot)
    if not snapshot_path.is_absolute():
        snapshot_path = (Path.cwd() / snapshot_path).resolve()
    snapshot = json.loads(snapshot_path.read_text())
    ignore = list(snapshot.get("ignore", DEFAULT_IGNORES)) + args.ignore
    before = snapshot.get("files", {})
    after = snapshot_state(repo, ignore)
    changed = changed_files(before, after)

    state = load_state()
    mode = role_mode(args.role, args.mode)
    allowed = state_patterns(state, "allowed_files") + args.allowed
    forbidden = state_patterns(state, "forbidden_files") + args.forbidden
    violations = violations_for(args.role, mode, changed, allowed, forbidden)
    check = {
        "id": f"file-guard-check-{compact_ts()}",
        "created_at": now(),
        "role": args.role,
        "mode": mode,
        "snapshot": str(snapshot_path),
        "changed_files": changed,
        "violations": violations,
        "allowed_patterns": allowed,
        "forbidden_patterns": forbidden,
        "ignore_patterns": ignore,
    }
    record_guard_check(state, check)

    if violations and args.open_blocker:
        add_blocker(
            state,
            args.role,
            f"File guard violation by {args.role}: {len(violations)} unauthorized file change(s)",
            "; ".join(violations[:10]),
        )
    save_state(state)
    log_event("File Guard", "check", f"{args.role} violations={len(violations)}")
    print(json.dumps(check, indent=2, sort_keys=True))
    return 1 if violations else 0


def main() -> int:
    args = parse_args()
    if args.command == "snapshot":
        return cmd_snapshot(args)
    if args.command == "check":
        return cmd_check(args)
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
