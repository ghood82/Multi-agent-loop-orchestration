"""Unit tests for the release gate's evaluation logic."""

from __future__ import annotations

from _helpers import load_source, ns

rg = load_source("release_gate", "release-gate.py")


def args(**kw):
    base = {
        "mode": "status",
        "require_ci_pass": False,
        "require_human_approval": False,
        "require_watchdog_pass": True,
        "require_latest_eval_pass": False,
        "allow_draft_pr": False,
        "allow_review_pending": False,
        "strict_file_guard": False,
    }
    base.update(kw)
    return ns(**base)


def test_clean_state_passes():
    state = {"watchdog": {"last_verdict": "PASS"}, "open_blockers": []}
    decision, blocking, _ = rg.evaluate(args(), state, {}, "")
    assert decision == "PASS", blocking


def test_open_blocker_stops():
    state = {"watchdog": {"last_verdict": "PASS"}, "open_blockers": [{"status": "open"}]}
    decision, blocking, _ = rg.evaluate(args(), state, {}, "")
    assert decision == "STOP"
    assert any("open blocker" in b for b in blocking)


def test_missing_watchdog_stops():
    decision, blocking, _ = rg.evaluate(args(), {"open_blockers": []}, {}, "")
    assert decision == "STOP"
    assert any("Watchdog" in b for b in blocking)


def test_ci_failure_is_waiting_not_stop():
    state = {
        "watchdog": {"last_verdict": "PASS"},
        "open_blockers": [],
        "ci_status": {"conclusion": "failure"},
    }
    decision, blocking, _ = rg.evaluate(args(require_ci_pass=True), state, {}, "")
    assert decision == "WAITING"
    assert any("CI is not passing" in b for b in blocking)


def test_require_human_approval_missing_stops():
    state = {"watchdog": {"last_verdict": "PASS"}, "open_blockers": []}
    decision, blocking, _ = rg.evaluate(args(require_human_approval=True), state, {}, "")
    assert decision == "STOP"
    assert any("human approval" in b.lower() for b in blocking)


def test_draft_pr_blocks_as_waiting():
    state = {"watchdog": {"last_verdict": "PASS"}, "open_blockers": []}
    pr = {"state": "OPEN", "isDraft": True}
    decision, blocking, _ = rg.evaluate(args(mode="merge"), state, pr, "")
    assert decision == "WAITING"
    assert any("draft" in b.lower() for b in blocking)


def test_latest_eval_pass_from_state_scalar():
    state = {
        "watchdog": {"last_verdict": "PASS"},
        "open_blockers": [],
        "last_eval_result": "PASS",
    }
    decision, _, _ = rg.evaluate(args(require_latest_eval_pass=True), state, {}, "")
    assert decision == "PASS"
