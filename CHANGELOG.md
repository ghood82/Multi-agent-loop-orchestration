# Changelog

## 0.4.0 - 2026-07-13

- Added `orchestration_state.py`: concurrency-safe state access with atomic writes (temp file + `os.replace`) and a re-entrant advisory `flock` held across each read-modify-write, so concurrent processes (daemon, hand-run scripts, parallel subagents) no longer silently clobber each other's `state.json` updates or leave a half-written file.
- Migrated the integrity-critical state mutators — `update-state.py`, `normalize-report.py`, `write-lock.py`, `decision-gate.py`, `phase-gate.py`, `release-gate.py` — to the shared locked/atomic helpers.
- Added a concurrency test proving 20 racing writers lose no updates (the same scenario dropped ~60% of writes before the lock), plus unit tests for atomic write, round-trip, and re-entrancy.
- Runtime lock/temp files (`.state.lock`, `.state.*.tmp`) are git-ignored.

## 0.3.0 - 2026-07-13

- Added a machine-readable result contract: roles emit an `orchestration-result` JSON block that `normalize-report.py` treats as authoritative instead of scraping verdicts from prose. Every role prompt now appends the contract.
- `normalize-report.py --require-structured` (and `run-cycle.py --require-structured` / `gates.require_structured`) fail a role and open a blocker when the block is missing or malformed, so a role cannot silently pass without a real verdict.
- Verdicts are stamped with the commit SHA they reviewed (`state.json` `role_verdicts`), and `run-cycle.py --require-fresh-evidence` (/ `gates.require_fresh_evidence`) blocks strict-gated actions when a required verdict is not bound to the current HEAD — closing the stale-evidence gap where a PASS for an old commit could gate newer code.
- Added tests covering contract parsing, structured-vs-prose precedence, SHA stamping, and evidence freshness.

## 0.2.0 - 2026-07-07

- Added `enforce-write-lock.py`: git-boundary enforcement of the production-code write lock (staged, base-ref, range, and explicit-path modes).
- Added `write-lock.py` (`acquire` / `release` / `status`) as the first-class way to manage the lock, keeping `state.json` and the `locks/production-code.lock` mirror in sync; `configure-project.py` now mirrors the lock file too, and `run-builder.sh` acquires the lock for Builder automatically.
- Added an installable pre-commit hook (`hooks/pre-commit`) and `install-hooks.py`, wired into `create_runtime_harness.py` and `adopt_project.py` to install automatically in git repos (with `--no-install-hooks` to opt out). Existing pre-commit hooks are preserved and chained.
- Added a `write-lock-check.yml` CI workflow template for the pull-request enforcement layer.
- Extended the smoke test with write-lock enforcement and hook-installation coverage.
- Added `pyproject.toml` with `orchestration-init`, `orchestration-adopt`, and `orchestration-smoke-test` console entry points.
- Documented enforcement in the harness README, root README, and runtime boundaries.
- Added a `tests/` pytest suite (49 tests) covering the write-lock enforcer, file guard, decision/phase/release gates, and hook installation, both as pure-function unit tests and installed-CLI integration tests.
- Added ruff (lint + format) and mypy quality gates via `pyproject.toml` and a `Lint` CI workflow; applied ruff formatting across the codebase.
- Expanded the smoke-test workflow to a Python 3.10–3.13 matrix and to run the unit tests.
- Added `docs/example-run.md`, a real captured end-to-end walkthrough of the write lock and gates on a throwaway repo.
- Clarified the skill's provider-neutral framing (agent skill packaged for Codex; harness drives Codex CLI, Claude Code, prompt-only, or a custom command).

## 0.1.0 - 2026-07-07

- Replaced placeholder license with MIT License.
- Updated public repository security and upload guidance.
- Prepared repository for GitHub upload.
- Added GitHub Actions smoke-test workflow.
- Added repository hygiene files and public-facing docs.
- Preserved the original operator guide at `docs/operator-guide.md`.
