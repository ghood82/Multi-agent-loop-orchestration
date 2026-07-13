"""Tests for the structured result contract, SHA-stamped verdicts, and freshness."""

from __future__ import annotations

import subprocess
from pathlib import Path

from _helpers import load_source, read_state, run_bin, write_state

nr = load_source("normalize_report", "normalize-report.py")
rc = load_source("run_cycle", "run-cycle.py")


def _write_report(repo: Path, name: str, body: str) -> Path:
    path = repo / "orchestration" / "reports" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _commit(repo: Path) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "c"], cwd=repo, check=True, capture_output=True)
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True
    )
    return out.stdout.strip()


# --- pure unit tests of the contract parser ---


def test_parse_structured_valid():
    result = nr.parse_structured('```orchestration-result\n{"verdict": "PASS"}\n```')
    assert result["ok"] is True
    assert result["data"]["verdict"] == "PASS"


def test_parse_structured_missing_block():
    assert nr.parse_structured("no block here")["found"] is False


def test_parse_structured_malformed_json():
    result = nr.parse_structured("```orchestration-result\n{bad json}\n```")
    assert result["found"] is True
    assert result["ok"] is False


def test_parse_structured_missing_verdict():
    result = nr.parse_structured('```orchestration-result\n{"summary": "x"}\n```')
    assert result["found"] is True
    assert result["ok"] is False


# --- integration: contract is authoritative and verdicts are SHA-stamped ---


def test_structured_block_is_authoritative_and_sha_stamped(harness_repo: Path):
    sha = _commit(harness_repo)
    body = (
        "# qa report\n\nThe tests PASS everywhere in this prose sentence.\n\n"
        '```orchestration-result\n{"verdict": "REQUEST_FIXES", "blockers": ["fix edge case"]}\n```\n'
    )
    report = _write_report(harness_repo, "r-qa.md", body)
    result = run_bin(
        harness_repo, "normalize-report.py", str(report), "--role", "qa", "--open-blockers"
    )
    assert result.returncode == 0
    verdict = read_state(harness_repo)["role_verdicts"]["qa"]
    # Structured verdict wins over the misleading "PASS" in prose.
    assert verdict["verdict"] == "REQUEST_FIXES"
    assert verdict["commit"] == sha
    assert verdict["structured"] is True
    assert any(
        "fix edge case" in b.get("description", "")
        for b in read_state(harness_repo).get("open_blockers", [])
    )


def test_require_structured_fails_on_missing_block(harness_repo: Path):
    report = _write_report(harness_repo, "r-sec.md", "# security report\n\nNo result block.\n")
    result = run_bin(
        harness_repo,
        "normalize-report.py",
        str(report),
        "--role",
        "security",
        "--require-structured",
    )
    assert result.returncode == 1
    assert any(
        "result contract" in b.get("description", "")
        for b in read_state(harness_repo).get("open_blockers", [])
    )


def test_prose_fallback_without_flag(harness_repo: Path):
    report = _write_report(harness_repo, "r-qa2.md", "# qa report\n\nVerdict: PASS\n")
    result = run_bin(harness_repo, "normalize-report.py", str(report), "--role", "qa")
    assert result.returncode == 0
    assert read_state(harness_repo)["role_verdicts"]["qa"]["verdict"] == "PASS"


# --- freshness: stale verdicts must not gate a newer commit ---


def test_stale_evidence_detects_commit_mismatch(harness_repo: Path):
    orch = harness_repo / "orchestration"
    sha = _commit(harness_repo)
    state = read_state(harness_repo)
    state["role_verdicts"] = {
        "eval": {"verdict": "PASS", "commit": sha},
        "watchdog": {"verdict": "PASS", "commit": "0000000000stale"},
    }
    write_state(harness_repo, state)
    assert rc.stale_evidence(orch, ["eval"]) is None
    assert rc.stale_evidence(orch, ["watchdog"]) is not None
    assert rc.stale_evidence(orch, ["eval", "watchdog"]) is not None


def test_stale_evidence_flags_unstamped_verdict(harness_repo: Path):
    orch = harness_repo / "orchestration"
    _commit(harness_repo)
    state = read_state(harness_repo)
    state["role_verdicts"] = {}  # no verdict recorded for this commit
    write_state(harness_repo, state)
    assert rc.stale_evidence(orch, ["eval"]) is not None
