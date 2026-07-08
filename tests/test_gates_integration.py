"""End-to-end tests that drive the installed gate scripts as subprocesses.

These prove the CLI wiring, exit codes, and JSON output of the real installed
harness, complementing the pure-function unit tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _helpers import read_state, run_bin, write_state


def test_decision_gate_high_risk_requires_human(harness_repo: Path):
    result = run_bin(
        harness_repo,
        "decision-gate.py",
        "--risk",
        "high",
        "--decision",
        "Change auth",
        "--evidence",
        "reports/json/x.json",
        "--json",
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["decision"] == "HUMAN_REQUIRED"


def test_decision_gate_low_risk_autonomous(harness_repo: Path):
    result = run_bin(
        harness_repo,
        "decision-gate.py",
        "--risk",
        "low",
        "--decision",
        "Rerun tests",
        "--evidence",
        "reports/json/x.json",
        "--json",
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "APPROVED_AUTONOMOUS"


def test_phase_gate_fresh_state_stops(harness_repo: Path):
    result = run_bin(harness_repo, "phase-gate.py", "--json", "--strict")
    assert result.returncode == 1
    assert json.loads(result.stdout)["verdict"] == "STOP"


def test_enforce_write_lock_installed_cli(harness_repo: Path):
    # Template state ships an inactive lock.
    blocked = run_bin(
        harness_repo,
        "enforce-write-lock.py",
        "--paths",
        "src/app.py",
        "--require-active-lock",
        "--json",
    )
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["ok"] is False

    allowed = run_bin(
        harness_repo,
        "enforce-write-lock.py",
        "--paths",
        "src/app.py",
        "--no-require-active-lock",
        "--json",
    )
    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["ok"] is True


def test_hook_installed_by_default(harness_repo: Path):
    # create_runtime_harness installs the hook automatically in a git repo.
    assert (harness_repo / ".git" / "hooks" / "pre-commit").exists()
    result = run_bin(harness_repo, "install-hooks.py", "--check")
    assert result.returncode == 0


def test_health_check_runs_and_emits_json(harness_repo: Path):
    # health-check emits JSON by default (--summary switches to text).
    result = run_bin(harness_repo, "health-check.py")
    assert result.returncode in {0, 1}
    payload = json.loads(result.stdout)
    assert "status" in payload or "failures" in payload


def test_release_gate_missing_pr_metadata_file_records_stop(harness_repo: Path):
    state = read_state(harness_repo)
    state["watchdog"]["last_verdict"] = "PASS"
    write_state(harness_repo, state)

    result = run_bin(
        harness_repo,
        "release-gate.py",
        "--mode",
        "pr",
        "--pr-from-file",
        str(harness_repo / "missing-pr.json"),
    )

    assert result.returncode == 1
    assert "Traceback" not in result.stdout + result.stderr
    assert "Unable to read PR metadata file" in result.stdout
    state = read_state(harness_repo)
    assert state["release_gate"]["last_decision"] == "STOP"


def test_run_cycle_push_create_pr_watch_ci_release_gate_targets_created_pr(
    harness_repo: Path, tmp_path: Path
):
    state = read_state(harness_repo)
    state["watchdog"]["last_verdict"] = "PASS"
    write_state(harness_repo, state)

    subprocess.run(["git", "add", "."], cwd=harness_repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial harness"], cwd=harness_repo, check=True)
    subprocess.run(["git", "switch", "-c", "feature/pr-identity"], cwd=harness_repo, check=True)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=harness_repo, check=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_log = tmp_path / "gh-calls.jsonl"
    pr_url = "https://github.com/example/repo/pull/42"
    fake_gh.write_text(
        f"""#!{sys.executable}
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as handle:
    handle.write(json.dumps(args) + "\\n")

if args[:2] == ["pr", "create"]:
    print({pr_url!r})
    raise SystemExit(0)

if args[:2] == ["pr", "checks"]:
    print(json.dumps([
        {{"bucket": "pass", "name": "smoke-test", "workflow": "Smoke test", "link": "https://example.invalid/check"}}
    ]))
    raise SystemExit(0)

if args[:2] == ["pr", "view"]:
    print(json.dumps({{
        "number": 42,
        "url": {pr_url!r},
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "reviewDecision": "",
        "headRefName": "feature/pr-identity",
        "baseRefName": "main"
    }}))
    raise SystemExit(0)

print("unexpected gh arguments: " + json.dumps(args), file=sys.stderr)
raise SystemExit(2)
"""
    )
    fake_gh.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["FAKE_GH_LOG"] = str(fake_log)
    env["AGENT_PROVIDER"] = "prompt-only"
    result = subprocess.run(
        [
            "bash",
            "orchestration/bin/run-cycle.sh",
            "--roles",
            "docs",
            "--allow-git-write",
            "--push",
            "--create-pr",
            "--watch-ci",
            "--ci-required",
            "--release-gate",
            "--release-mode",
            "pr",
            "--require-ci-pass",
        ],
        cwd=harness_repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    state = read_state(harness_repo)
    assert state["active_pr"] == pr_url
    assert state["ci_status"]["pr"] == pr_url
    assert state["release_gate"]["last_decision"] == "PASS"

    gh_calls = [json.loads(line) for line in fake_log.read_text().splitlines()]
    assert any(call[:2] == ["pr", "checks"] and call[-1] == pr_url for call in gh_calls)
    assert any(call[:2] == ["pr", "view"] and call[-1] == pr_url for call in gh_calls)
