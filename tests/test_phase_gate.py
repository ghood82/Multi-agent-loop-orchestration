"""Unit tests for the phase gate's check builder."""

from __future__ import annotations

from _helpers import load_source, ns

pg = load_source("phase_gate", "phase-gate.py")


def args(**kw):
    base = {
        "advance_to": "",
        "require_security": False,
        "skip_security": False,
        "require_human_approval": False,
        "skip_policy_audit": True,
    }
    base.update(kw)
    return ns(**base)


def all_pass_state():
    return {
        "current_phase": "Phase 1",
        "open_blockers": [],
        "last_qa_result": "PASS",
        "last_security_result": "PASS",
        "last_eval_result": "PASS",
        "watchdog": {"last_verdict": "PASS"},
        "last_architect_decision": "APPROVED",
        "policy_audit": {"last_decision": "PASS"},
        "human_approval_required": False,
    }


def test_fresh_state_stops():
    # A freshly configured phase gate has TBD evidence everywhere -> STOP.
    report = pg.build_report(args(), {"current_phase": "Phase 1"})
    assert report["verdict"] == "STOP"
    assert report["blocking"]


def test_all_evidence_present_passes():
    report = pg.build_report(args(), all_pass_state())
    assert report["verdict"] == "PASS", report["blocking"]


def test_open_blocker_blocks():
    state = all_pass_state()
    state["open_blockers"] = [{"status": "open"}]
    report = pg.build_report(args(), state)
    assert report["verdict"] == "STOP"
    assert any(c["name"] == "open_blockers" and c["status"] == "BLOCKING" for c in report["checks"])


def test_security_required_when_high_risk_area_present():
    state = all_pass_state()
    state["last_security_result"] = "missing"
    state["high_risk_areas"] = ["auth"]
    report = pg.build_report(args(), state)
    security = next(c for c in report["checks"] if c["name"] == "security_pass")
    assert security["required"] is True
    assert security["status"] == "BLOCKING"


def test_security_skipped_when_flagged():
    state = all_pass_state()
    state["last_security_result"] = "missing"
    state["high_risk_areas"] = ["auth"]
    report = pg.build_report(args(skip_security=True), state)
    security = next(c for c in report["checks"] if c["name"] == "security_pass")
    assert security["required"] is False
    assert report["verdict"] == "PASS"


def test_human_approval_required_blocks_without_artifact():
    state = all_pass_state()
    report = pg.build_report(args(require_human_approval=True), state)
    human = next(c for c in report["checks"] if c["name"] == "human_approval")
    assert human["required"] is True
    assert human["status"] == "BLOCKING"
    assert report["verdict"] == "STOP"
