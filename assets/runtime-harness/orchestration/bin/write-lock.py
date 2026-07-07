#!/usr/bin/env python3
"""Acquire, release, and inspect the production-code write lock.

This is the first-class way to manage the single-writer invariant. It keeps the
two representations of the lock in sync:

- ``state.json`` -> ``write_lock`` is the source of truth read by
  ``enforce-write-lock.py`` (the git pre-commit hook and CI check).
- ``locks/production-code.lock`` is the human-readable mirror read by the shell
  role runners (``run-builder.sh`` and friends).

Keeping them in one command prevents the drift that would otherwise let the
enforcer and the runners disagree about who holds the lock.

    write-lock.py acquire --owner Builder --allowed 'src/**'
    write-lock.py release
    write-lock.py status
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
LOCK_FILE = ROOT / "locks" / "production-code.lock"
EVENT_LOG = ROOT / "events.log"

LOCK_FIELDS = ("status", "owner", "scope", "allowed_files", "forbidden_files")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    try:
        state = json.loads(STATE_FILE.read_text())
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing state file: {STATE_FILE}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise SystemExit("state.json must contain an object.")
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": "write-lock", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def as_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def current_lock(state: dict[str, Any]) -> dict[str, Any]:
    lock = state.get("write_lock")
    return lock if isinstance(lock, dict) else {}


def mirror_lock_file(lock: dict[str, Any]) -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": lock.get("status", "inactive"),
        "owner": lock.get("owner", "Builder"),
        "scope": lock.get("scope", ""),
        "allowed_files": as_list(lock.get("allowed_files")),
        "forbidden_files": as_list(lock.get("forbidden_files")),
        "updated_at": now(),
    }
    LOCK_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def emit(result: dict[str, Any], as_json: bool, text: str) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(text)


def cmd_acquire(args: argparse.Namespace) -> int:
    state = load_state()
    lock = current_lock(state)
    active = str(lock.get("status", "inactive")).lower() == "active"
    held_by = lock.get("owner", "Builder")
    owner = args.owner or held_by or "Builder"

    if active and str(held_by) != str(owner) and not args.force:
        emit(
            {"status": "active", "owner": held_by, "acquired": False},
            args.json,
            f"Refusing to acquire: write lock is already held by {held_by}. "
            f"Use --force to override or have {held_by} release it first.",
        )
        return 2

    scope = args.scope or lock.get("scope") or state.get("current_phase", "")
    allowed = (
        args.allowed
        if args.allowed
        else as_list(lock.get("allowed_files")) or as_list(state.get("allowed_files"))
    )
    forbidden = (
        args.forbidden
        if args.forbidden
        else as_list(lock.get("forbidden_files")) or as_list(state.get("forbidden_files"))
    )

    new_lock = {
        "status": "active",
        "owner": owner,
        "scope": scope,
        "allowed_files": allowed,
        "forbidden_files": forbidden,
    }
    state["write_lock"] = new_lock
    state["active_writer"] = owner
    save_state(state)
    mirror_lock_file(new_lock)
    log_event("acquired", f"{owner} scope={scope}")
    emit(
        {"acquired": True, **new_lock},
        args.json,
        f"Write lock acquired by {owner} (scope: {scope or 'unset'}; "
        f"allowed: {', '.join(allowed) or 'unrestricted'}).",
    )
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    state = load_state()
    lock = current_lock(state)
    owner = args.owner or lock.get("owner", "Builder")
    lock["status"] = "inactive"
    lock.setdefault("owner", owner)
    state["write_lock"] = lock
    save_state(state)
    mirror_lock_file(lock)
    log_event("released", str(owner))
    emit(
        {"released": True, "owner": owner, "status": "inactive"},
        args.json,
        f"Write lock released ({owner}).",
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state = load_state()
    lock = current_lock(state)
    mirror = {}
    if LOCK_FILE.exists():
        try:
            mirror = json.loads(LOCK_FILE.read_text())
        except json.JSONDecodeError:
            mirror = {}
    out_of_sync = any(
        as_list(lock.get(field)) != as_list(mirror.get(field))
        if field.endswith("_files")
        else str(lock.get(field, "")) != str(mirror.get(field, ""))
        for field in LOCK_FIELDS
    )
    result = {
        "status": lock.get("status", "inactive"),
        "owner": lock.get("owner"),
        "scope": lock.get("scope"),
        "allowed_files": as_list(lock.get("allowed_files")),
        "forbidden_files": as_list(lock.get("forbidden_files")),
        "mirror_out_of_sync": out_of_sync,
    }
    text = (
        f"Write lock: {result['status']} (owner: {result['owner']}, "
        f"scope: {result['scope'] or 'unset'})"
    )
    if out_of_sync:
        text += "\nWARNING: production-code.lock is out of sync; run acquire/release to reconcile."
    emit(result, args.json, text)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    acquire = sub.add_parser("acquire", help="Acquire the production-code write lock.")
    acquire.add_argument("--owner", default="", help="Lock owner (default: Builder).")
    acquire.add_argument("--scope", default="", help="Scope note (default: current phase).")
    acquire.add_argument(
        "--allowed", action="append", default=[], help="Allowed glob (repeatable)."
    )
    acquire.add_argument(
        "--forbidden", action="append", default=[], help="Forbidden glob (repeatable)."
    )
    acquire.add_argument("--force", action="store_true", help="Take a lock held by another owner.")
    acquire.add_argument("--json", action="store_true")

    release = sub.add_parser("release", help="Release the production-code write lock.")
    release.add_argument("--owner", default="", help="Owner releasing the lock (for the log).")
    release.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="Show the current lock and mirror sync state.")
    status.add_argument("--json", action="store_true")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "acquire":
        return cmd_acquire(args)
    if args.command == "release":
        return cmd_release(args)
    if args.command == "status":
        return cmd_status(args)
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
