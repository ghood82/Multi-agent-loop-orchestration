# Changelog

## 0.2.0 - 2026-07-07

- Added `enforce-write-lock.py`: git-boundary enforcement of the production-code write lock (staged, base-ref, range, and explicit-path modes).
- Added an installable pre-commit hook (`hooks/pre-commit`) and `install-hooks.py`, wired into `create_runtime_harness.py` and `adopt_project.py` to install automatically in git repos (with `--no-install-hooks` to opt out). Existing pre-commit hooks are preserved and chained.
- Added a `write-lock-check.yml` CI workflow template for the pull-request enforcement layer.
- Extended the smoke test with write-lock enforcement and hook-installation coverage.
- Added `pyproject.toml` with `orchestration-init`, `orchestration-adopt`, and `orchestration-smoke-test` console entry points.
- Documented enforcement in the harness README, root README, and runtime boundaries.

## 0.1.0 - 2026-07-07

- Replaced placeholder license with MIT License.
- Updated public repository security and upload guidance.
- Prepared repository for GitHub upload.
- Added GitHub Actions smoke-test workflow.
- Added repository hygiene files and public-facing docs.
- Preserved the original operator guide at `docs/operator-guide.md`.
