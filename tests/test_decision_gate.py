"""Unit tests for the decision gate's risk classification."""

from __future__ import annotations

from _helpers import load_source, ns

dg = load_source("decision_gate", "decision-gate.py")


def args(**kw):
    base = {
        "risk": "low",
        "decision": "Do the thing",
        "evidence": ["reports/json/x.json"],
        "research_summary": "",
        "confidence": None,
        "human_recommended": False,
    }
    base.update(kw)
    return ns(**base)


def test_low_risk_with_evidence_is_autonomous():
    report = dg.build_report(args(risk="low"), {})
    assert report["decision"] == "APPROVED_AUTONOMOUS"
    assert report["human_required"] is False


def test_low_risk_missing_evidence_requests_evidence():
    report = dg.build_report(args(risk="low", evidence=[]), {})
    assert report["decision"] == "REQUEST_EVIDENCE"
    assert "evidence" in report["missing_evidence"]


def test_high_risk_requires_human():
    report = dg.build_report(args(risk="high"), {})
    assert report["decision"] == "HUMAN_REQUIRED"
    assert report["human_required"] is True


def test_medium_risk_above_threshold_is_approved():
    report = dg.build_report(
        args(risk="medium", research_summary="Compared options", confidence=0.9), {}
    )
    assert report["decision"] == "APPROVED_AFTER_RESEARCH"


def test_medium_risk_below_threshold_recommends_human():
    report = dg.build_report(
        args(risk="medium", research_summary="Compared options", confidence=0.5), {}
    )
    assert report["decision"] == "HUMAN_RECOMMENDED"


def test_medium_risk_without_research_requests_evidence():
    report = dg.build_report(args(risk="medium", research_summary="", confidence=0.9), {})
    assert report["decision"] == "REQUEST_EVIDENCE"
    assert "research_summary" in report["missing_evidence"]


def test_threshold_comes_from_state_policy():
    state = {"decision_policy": {"medium_risk": {"confidence_threshold": 0.95}}}
    report = dg.build_report(args(risk="medium", research_summary="ok", confidence=0.9), state)
    assert report["confidence_threshold"] == 0.95
    assert report["decision"] == "HUMAN_RECOMMENDED"  # 0.9 < 0.95
