"""Concurrency-safe helpers for reading and writing ``orchestration/state.json``.

The orchestration harness is a shared-mutable-state coordinator: the daemon, a
hand-run script, and parallel subagents can all read-modify-write the same
``state.json``. Plain ``read_text`` / ``write_text`` loses updates under that
concurrency (last writer wins, silently dropping another loop's blocker or
verdict) and can leave a half-written, invalid file.

This module fixes both:

- ``write_atomic`` writes to a temp file in the same directory and ``os.replace``s
  it into place, so a reader never sees a partial file.
- ``begin`` / ``commit`` hold an advisory ``flock`` across the whole
  read-modify-write, so concurrent processes serialize instead of clobbering.
  ``begin`` is re-entrant within a process (a script may load state more than
  once without self-deadlocking).

Scripts delegate their existing ``load_state`` / ``save_state`` to ``begin`` /
``commit``; the lock is held from the load until the matching save (or until the
process exits, since ``flock`` releases automatically).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

try:
    import fcntl

    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - non-POSIX platforms
    _HAVE_FCNTL = False

# key (lock path) -> [file handle or None, reentrancy count]
_HELD: dict[str, list[Any]] = {}


def _lock_path(state_path: Path) -> Path:
    return state_path.parent / ".state.lock"


def read(state_path: Path) -> dict[str, Any]:
    """Read and validate state.json, raising SystemExit on a bad/missing file."""
    try:
        data = json.loads(Path(state_path).read_text())
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing state file: {state_path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("state.json must contain an object.")
    return data


def write_atomic(state_path: Path, data: dict[str, Any]) -> None:
    """Write state.json atomically (temp file + os.replace), never a partial file."""
    state_path = Path(state_path)
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(state_path.parent), prefix=".state.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, state_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def begin(state_path: Path) -> dict[str, Any]:
    """Acquire the advisory lock (re-entrant) and return the current state."""
    state_path = Path(state_path)
    key = str(_lock_path(state_path))
    if key in _HELD:
        _HELD[key][1] += 1
    elif _HAVE_FCNTL:
        # Held open until commit (or process exit) so the flock stays held.
        handle = open(key, "w")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        _HELD[key] = [handle, 1]
    else:  # pragma: no cover - non-POSIX: atomic write only, no locking
        _HELD[key] = [None, 1]
    return read(state_path)


def commit(state_path: Path, data: dict[str, Any]) -> None:
    """Atomically write state and release the lock acquired by ``begin``."""
    state_path = Path(state_path)
    write_atomic(state_path, data)
    key = str(_lock_path(state_path))
    held = _HELD.get(key)
    if not held:
        return  # commit without a matching begin: the atomic write still stands.
    held[1] -= 1
    if held[1] <= 0:
        handle = held[0]
        if handle is not None and _HAVE_FCNTL:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
        _HELD.pop(key, None)
