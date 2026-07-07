#!/usr/bin/env python3
"""Smoke-test the generated runtime harness from this skill package."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
CREATE_HARNESS = SKILL_ROOT / "scripts" / "create_runtime_harness.py"
ADOPT_PROJECT = SKILL_ROOT / "scripts" / "adopt_project.py"


def run(
    command: list[str],
    cwd: Path,
    *,
    expect: int = 0,
    label: str = "",
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != expect:
        heading = f"{label}: " if label else ""
        raise AssertionError(
            f"{heading}{' '.join(command)} returned {result.returncode}, expected {expect}\n{result.stdout}"
        )
    return result


def load_state(repo: Path) -> dict[str, Any]:
    state_path = repo / "orchestration" / "state.json"
    return json.loads(state_path.read_text())


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(value: Any, label: str) -> None:
    if not value:
        raise AssertionError(label)


def assert_file(repo: Path, relative: str) -> None:
    path = repo / relative
    if not path.exists():
        raise AssertionError(f"Missing generated file: {relative}")


def smoke_test(keep: bool) -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="multi-agent-orchestration-smoke-"))
    repo = temp_root / "repo"
    adopted_repo = temp_root / "adopted-repo"
    repo.mkdir()
    adopted_repo.mkdir()
    passed = False

    try:
        run(["git", "init"], adopted_repo, label="git init adopted")
        adopted = run(
            [
                sys.executable,
                str(ADOPT_PROJECT),
                "--target",
                str(adopted_repo),
                "--project-name",
                "Adopted Smoke Project",
                "--repo-name",
                "adopted-smoke-repo",
                "--roadmap-name",
                "Adopted Smoke Roadmap",
                "--current-phase",
                "Adopted Phase 1",
                "--current-objective",
                "Install and configure orchestration in one command.",
                "--test-command",
                "pytest",
                "--preserved-component",
                "existing API",
                "--forbidden-change",
                "do not rewrite persistence",
                "--policy-profile",
                "standard",
                "--json",
            ],
            SKILL_ROOT,
            label="adopt project",
        )
        adopted_json = json.loads(adopted.stdout)
        assert_equal(adopted_json["project"], "Adopted Smoke Project", "adopted project name")
        assert_true((adopted_repo / "orchestration" / "bin" / "setup-intake.py").exists(), "adopted setup intake exists")
        assert_true((adopted_repo / "orchestration" / "bin" / "ops-check.py").exists(), "adopted ops check exists")
        assert_true((adopted_repo / "orchestration" / "bin" / "agent-adapter.py").exists(), "adopted agent adapter exists")
        assert_true((adopted_repo / "orchestration" / "bin" / "configure-agent-provider.py").exists(), "adopted provider config exists")
        assert_true((adopted_repo / "orchestration" / "bin" / "doctor.py").exists(), "adopted doctor exists")
        assert_true((adopted_repo / "orchestration" / "bin" / "requirements-matrix.py").exists(), "adopted requirements matrix exists")
        assert_true(adopted_json["builder_handoff"].get("path"), "adopter should create builder handoff")
        adopted_state = load_state(adopted_repo)
        assert_equal(adopted_state["setup_intake"]["applied"], True, "adopter setup intake applied")
        assert_true(adopted_state["ops_check"]["last_decision"] in {"PASS", "FAIL"}, "adopter should record ops check verdict")
        assert_true(adopted_state.get("handoff_packets"), "adopter should record a handoff packet")

        run(["git", "init"], repo, label="git init")
        run(
            [
                sys.executable,
                str(CREATE_HARNESS),
                "--target",
                str(repo),
                "--project-name",
                "Smoke Project",
                "--repo-name",
                "smoke-repo",
                "--roadmap-name",
                "Smoke Roadmap",
                "--current-phase",
                "Phase 1",
                "--current-objective",
                "Prove generated orchestration harness works.",
                "--state-file-path",
                "docs/project-roadmap-state.md",
                "--test-command",
                "pytest",
            ],
            SKILL_ROOT,
            label="create harness",
        )

        for relative in [
            "orchestration/README.md",
            "orchestration/state.json",
            "orchestration/agent-adapter.json",
            "orchestration/operating-policy.json",
            "orchestration/bin/agent-adapter.py",
            "orchestration/bin/configure-agent-provider.py",
            "orchestration/bin/decision-gate.py",
            "orchestration/bin/prepare-watchdog-evidence.py",
            "orchestration/bin/setup-intake.py",
            "orchestration/bin/configure-project.py",
            "orchestration/bin/health-check.py",
            "orchestration/bin/acceptance-audit.py",
            "orchestration/bin/sync-state-doc.py",
            "orchestration/bin/status.py",
            "orchestration/bin/operating-dashboard.py",
            "orchestration/bin/ops-check.py",
            "orchestration/bin/policy-audit.py",
            "orchestration/bin/phase-gate.py",
            "orchestration/bin/eval-fixture.py",
            "orchestration/bin/eval-result.py",
            "orchestration/bin/doctor.py",
            "orchestration/bin/requirements-matrix.py",
            "orchestration/bin/handoff-packet.py",
            "orchestration/bin/stop-report.py",
            "orchestration/bin/approval-request.py",
            "orchestration/bin/resume-plan.py",
            "orchestration/evals/fixtures/.gitkeep",
            "orchestration/evals/results/.gitkeep",
            "orchestration/evals/rubrics/project-quality-rubric.md",
            "orchestration/reports/agent-runs/.gitkeep",
            "orchestration/bin/run-remediation.sh",
        ]:
            assert_file(repo, relative)

        run(
            [
                sys.executable,
                "orchestration/bin/setup-intake.py",
                "--non-interactive",
                "--project-name",
                "Intake Smoke Project",
                "--repo-name",
                "intake-smoke-repo",
                "--roadmap-name",
                "Intake Smoke Roadmap",
                "--current-phase",
                "Intake Phase 1",
                "--current-objective",
                "Capture setup intake without blocking.",
                "--state-file-path",
                "docs/project-roadmap-state.md",
                "--test-command",
                "pytest",
                "--preserved-component",
                "existing parser",
                "--forbidden-change",
                "do not rewrite auth",
                "--blocker-mode",
                "bounded-recovery",
                "--blocker-recovery-limit",
                "2",
                "--agent-provider",
                "auto",
                "--decision-policy-profile",
                "risk-bucketed",
                "--policy-profile",
                "standard",
                "--apply",
                "--json",
            ],
            repo,
            label="setup intake",
        )
        state = load_state(repo)
        assert_equal(state["setup_intake"]["applied"], True, "setup intake applied")
        assert_equal(state["blocking_policy"]["mode"], "bounded-recovery", "setup intake blocker mode")
        assert_equal(state["blocking_policy"]["recovery_limit"], 2, "setup intake recovery limit")
        assert_equal(state["agent_adapter"]["configured_provider"], "auto", "setup intake agent provider")
        assert_true("medium_risk" in state["decision_policy"], "setup intake decision policy")

        prompt_only = run(
            [
                sys.executable,
                "orchestration/bin/agent-adapter.py",
                "--role",
                "smoke",
                "--prompt-file",
                "orchestration/README.md",
                "--provider",
                "prompt-only",
                "--json",
            ],
            repo,
            label="agent adapter prompt-only",
        )
        prompt_only_json = json.loads(prompt_only.stdout)
        assert_equal(prompt_only_json["provider"], "prompt-only", "prompt-only provider")
        assert_equal(prompt_only_json["exit_code"], 0, "prompt-only exit code")
        assert_true("Prompt prepared" in prompt_only_json["stdout"], "prompt-only stdout")

        provider_list = run(
            [sys.executable, "orchestration/bin/configure-agent-provider.py", "--list", "--json"],
            repo,
            label="provider list",
        )
        provider_list_json = json.loads(provider_list.stdout)
        assert_true("auto" in provider_list_json["providers"], "auto provider preset should exist")
        assert_true("codex-cli" in provider_list_json["providers"], "codex-cli preset should exist")
        assert_true("claude-code" in provider_list_json["providers"], "claude-code preset should exist")
        assert_true("custom-command" in provider_list_json["providers"], "custom-command preset should exist")

        auto_resolve = run(
            [
                sys.executable,
                "orchestration/bin/agent-adapter.py",
                "--role",
                "auto-resolve-smoke",
                "--prompt-file",
                "orchestration/README.md",
                "--provider",
                "auto",
                "--resolve-only",
                "--json",
            ],
            repo,
            label="agent adapter auto resolve",
        )
        auto_resolve_json = json.loads(auto_resolve.stdout)
        assert_equal(auto_resolve_json["provider"], "auto", "auto provider")
        assert_true(auto_resolve_json["resolved_provider"] in {"codex-cli", "claude-code", "prompt-only"}, "auto resolved provider")

        provider_config = run(
            [
                sys.executable,
                "orchestration/bin/configure-agent-provider.py",
                "--provider",
                "custom-command",
                "--command",
                f"{sys.executable} -c \"import sys; data=sys.stdin.read(); print('configured-provider-ok', len(data))\"",
                "--test",
                "--json",
            ],
            repo,
            label="provider configure custom command",
        )
        provider_config_json = json.loads(provider_config.stdout)
        assert_equal(provider_config_json["config"]["active_provider"], "custom-command", "configured active provider")
        assert_equal(provider_config_json["test"]["exit_code"], 0, "provider config test exit")
        assert_true("configured-provider-ok" in provider_config_json["test"]["result"]["stdout"], "provider config test output")
        state = load_state(repo)
        assert_equal(state["agent_adapter"]["configured_provider"], "custom-command", "configured provider state")

        adapter_run = run(
            [
                sys.executable,
                "orchestration/bin/agent-adapter.py",
                "--role",
                "smoke-command",
                "--prompt-file",
                "orchestration/README.md",
                "--provider",
                "command",
                "--argv",
                sys.executable,
                "--argv=-c",
                "--argv",
                "import sys; data=sys.stdin.read(); print('adapter-ok', len(data))",
                "--json",
            ],
            repo,
            label="agent adapter argv",
        )
        adapter_json = json.loads(adapter_run.stdout)
        assert_equal(adapter_json["provider"], "command", "command provider")
        assert_equal(adapter_json["exit_code"], 0, "command provider exit code")
        assert_true("adapter-ok" in adapter_json["stdout"], "command provider stdout")
        state = load_state(repo)
        assert_true(state.get("agent_runs"), "agent adapter should record runs")
        assert_equal(state["agent_adapter"]["last_role"], "smoke-command", "agent adapter last role")

        doctor = run(
            [sys.executable, "orchestration/bin/doctor.py", "--write-report", "--json", "--events", "2"],
            repo,
            label="doctor",
        )
        doctor_json = json.loads(doctor.stdout)
        assert_true(doctor_json["verdict"] in {"READY_PROMPT_ONLY", "CONTINUE", "CHECK_GATES", "REMEDIATE", "WAIT", "STOP"}, "doctor verdict")
        assert_true(doctor_json["next_command"], "doctor next command")
        state = load_state(repo)
        assert_true(state["doctor"]["last_report"], "doctor should record report")

        matrix = run(
            [sys.executable, "orchestration/bin/requirements-matrix.py", "--write-report", "--json", "--strict"],
            repo,
            label="requirements matrix",
        )
        matrix_json = json.loads(matrix.stdout)
        assert_equal(matrix_json["verdict"], "PASS", "requirements matrix verdict")
        assert_true(matrix_json["requirements_passed"] == matrix_json["requirements_total"], "requirements matrix all passed")
        state = load_state(repo)
        assert_equal(state["requirements_matrix"]["last_decision"], "PASS", "requirements matrix state")

        run(
            [
                sys.executable,
                "orchestration/bin/configure-project.py",
                "--project-name",
                "Configured Smoke Project",
                "--repo-name",
                "configured-smoke-repo",
                "--roadmap-name",
                "Configured Smoke Roadmap",
                "--current-phase",
                "Configured Phase 1",
                "--current-objective",
                "Configured objective.",
                "--preserved-component",
                "Document AI",
                "--forbidden-change",
                "Do not remove embeddings",
                "--allowed-file",
                "src/**",
                "--forbidden-file",
                "migrations/**",
                "--high-risk-area",
                "external APIs",
                "--blocker-mode",
                "bounded-recovery",
                "--blocker-recovery-limit",
                "1",
                "--policy-profile",
                "strict-pr",
                "--policy-require-latest-eval-pass",
                "true",
                "--sync-state-doc",
                "--json",
            ],
            repo,
            label="configure project",
        )
        state = load_state(repo)
        assert_equal(state["project_name"], "Configured Smoke Project", "configured project name")
        assert_equal(state["blocking_policy"]["mode"], "bounded-recovery", "configured blocker mode")
        assert_true("Document AI" in state["preserved_components"], "preserved component configured")
        assert_true("Do not remove embeddings" in state["forbidden_changes"], "forbidden change configured")
        policy = json.loads((repo / "orchestration" / "operating-policy.json").read_text())
        assert_equal(policy["profile"], "strict-pr", "configured policy profile")
        assert_equal(policy["gates"]["require_latest_eval_pass"], True, "configured eval policy gate")
        assert_file(repo, "docs/project-roadmap-state.md")

        eval_fixture = run(
            [
                sys.executable,
                "orchestration/bin/eval-fixture.py",
                "create",
                "--id",
                "wrong-domain-policy-match",
                "--name",
                "Wrong-domain policy match stays non-contradictory",
                "--description",
                "Protects against false positive contradiction verdicts from weak policy evidence.",
                "--input",
                "Procedure mentions annual review; policy evidence comes from unrelated credentialing section.",
                "--expected",
                "Do not classify as contradiction without same-domain policy evidence",
                "--tolerance",
                "May return needs-review when evidence is insufficient",
                "--risk",
                "false positive user-facing verdict",
                "--tag",
                "phase-1,policy-validation",
                "--write-report",
                "--json",
            ],
            repo,
            label="eval fixture",
        )
        eval_fixture_json = json.loads(eval_fixture.stdout)
        assert_file(repo, "orchestration/" + eval_fixture_json["fixture"])
        assert_file(repo, "orchestration/" + eval_fixture_json["markdown"])
        state = load_state(repo)
        assert_true(state.get("eval_fixtures"), "eval fixture should be recorded")
        assert_equal(state["last_eval_fixture"], "evals/fixtures/wrong-domain-policy-match.json", "last eval fixture")
        assert_equal(state["eval_quality_status"], "fixtures-updated", "eval quality status")

        drift_result = run(
            [
                sys.executable,
                "orchestration/bin/eval-result.py",
                "record",
                "--id",
                "wrong-domain-policy-match-drift",
                "--fixture",
                "evals/fixtures/wrong-domain-policy-match.json",
                "--verdict",
                "DRIFT",
                "--actual",
                '{"classification":"contradiction"}',
                "--diff",
                "Actual classification contradicted expected non-contradiction behavior",
                "--risk",
                "false positive user-facing verdict",
                "--recommended-next-action",
                "Builder should fix evidence-domain filtering and rerun Eval Monitor.",
                "--open-blocker",
                "--write-report",
                "--json",
            ],
            repo,
            label="eval drift result",
        )
        drift_result_json = json.loads(drift_result.stdout)
        assert_file(repo, "orchestration/" + drift_result_json["result"])
        assert_file(repo, "orchestration/" + drift_result_json["markdown"])
        state = load_state(repo)
        assert_true(state.get("eval_results"), "eval result should be recorded")
        assert_equal(state["last_eval_result"], "DRIFT", "drift eval result")
        assert_true(state.get("open_blockers"), "eval drift should open blocker")
        eval_blocker_id = state["open_blockers"][0]["id"]
        run(
            [
                sys.executable,
                "orchestration/bin/update-state.py",
                "resolve-blocker",
                eval_blocker_id,
                "--evidence",
                "Smoke test resolved synthetic eval drift.",
            ],
            repo,
            label="resolve eval drift blocker",
        )
        run(
            [
                sys.executable,
                "orchestration/bin/update-state.py",
                "record-report",
                "--role",
                "watchdog",
                "--status",
                "complete",
                "--verdict",
                "PASS",
                "--summary",
                "Synthetic watchdog pass for eval gate smoke test.",
            ],
            repo,
            label="record watchdog pass",
        )
        eval_gate_drift = run(
            [
                sys.executable,
                "orchestration/bin/release-gate.py",
                "--mode",
                "status",
            ],
            repo,
            expect=1,
            label="policy eval gate blocks drift",
        )
        eval_gate_drift_json = json.loads(eval_gate_drift.stdout)
        assert_equal(eval_gate_drift_json["last_decision"], "STOP", "eval gate drift decision")
        assert_true(
            any("Latest eval result is not PASS" in item for item in eval_gate_drift_json["blocking"]),
            "eval gate should explain drift block",
        )
        policy_audit_drift = run(
            [sys.executable, "orchestration/bin/policy-audit.py", "--write-report", "--json", "--strict"],
            repo,
            expect=1,
            label="policy audit blocks drift",
        )
        policy_audit_drift_json = json.loads(policy_audit_drift.stdout)
        assert_equal(policy_audit_drift_json["verdict"], "FAIL", "policy audit drift verdict")
        assert_true(
            any(item["name"] == "latest_eval_pass" for item in policy_audit_drift_json["missing_evidence"]),
            "policy audit should report missing eval pass",
        )
        pass_result = run(
            [
                sys.executable,
                "orchestration/bin/eval-result.py",
                "record",
                "--id",
                "wrong-domain-policy-match-pass",
                "--fixture",
                "evals/fixtures/wrong-domain-policy-match.json",
                "--verdict",
                "PASS",
                "--actual",
                '{"classification":"needs_review"}',
                "--diff",
                "No unacceptable drift detected",
                "--evidence",
                "smoke eval monitor",
                "--recommended-next-action",
                "Continue to Watchdog.",
                "--write-report",
                "--json",
            ],
            repo,
            label="eval pass result",
        )
        pass_result_json = json.loads(pass_result.stdout)
        assert_file(repo, "orchestration/" + pass_result_json["result"])
        state = load_state(repo)
        assert_equal(state["last_eval_result"], "PASS", "passing eval result")
        assert_equal(state["eval_quality_status"], "eval-pass", "passing eval quality status")
        evidence = run(
            [
                sys.executable,
                "orchestration/bin/prepare-watchdog-evidence.py",
                "--write-report",
                "--json",
                "--strict",
            ],
            repo,
            label="prepare watchdog evidence",
        )
        evidence_json = json.loads(evidence.stdout)
        assert_equal(evidence_json["verdict"], "PASS", "watchdog evidence verdict")
        assert_true(evidence_json["connected_tests"], "watchdog evidence connected tests")
        state = load_state(repo)
        assert_equal(state["watchdog_evidence"]["last_verdict"], "PASS", "watchdog evidence state")
        decision_low = run(
            [
                sys.executable,
                "orchestration/bin/decision-gate.py",
                "--risk",
                "low",
                "--decision",
                "Refresh generated watchdog evidence",
                "--evidence",
                state["watchdog_evidence"]["last_report"],
                "--json",
            ],
            repo,
            label="decision gate low risk",
        )
        decision_low_json = json.loads(decision_low.stdout)
        assert_equal(decision_low_json["decision"], "APPROVED_AUTONOMOUS", "low-risk decision")
        policy_audit_pass = run(
            [sys.executable, "orchestration/bin/policy-audit.py", "--write-report", "--json", "--strict"],
            repo,
            label="policy audit passes after eval pass",
        )
        policy_audit_pass_json = json.loads(policy_audit_pass.stdout)
        assert_equal(policy_audit_pass_json["verdict"], "PASS", "policy audit pass verdict")
        run(
            [
                sys.executable,
                "orchestration/bin/release-gate.py",
                "--mode",
                "status",
            ],
            repo,
            label="policy eval gate passes after pass result",
        )
        phase_gate_block = run(
            [sys.executable, "orchestration/bin/phase-gate.py", "--write-report", "--json", "--strict"],
            repo,
            expect=1,
            label="phase gate blocks missing evidence",
        )
        phase_gate_block_json = json.loads(phase_gate_block.stdout)
        assert_equal(phase_gate_block_json["verdict"], "STOP", "phase gate blocking verdict")
        assert_true(
            any(item["name"] == "qa_pass" for item in phase_gate_block_json["blocking"]),
            "phase gate should require QA evidence",
        )
        for role, verdict_value in [
            ("qa", "PASS"),
            ("security", "PASS"),
            ("architect", "APPROVED"),
        ]:
            run(
                [
                    sys.executable,
                    "orchestration/bin/update-state.py",
                    "record-report",
                    "--role",
                    role,
                    "--status",
                    "complete",
                    "--verdict",
                    verdict_value,
                    "--summary",
                    f"Synthetic {role} phase-gate evidence.",
                ],
                repo,
                label=f"record {role} phase evidence",
            )
        run(
            [
                sys.executable,
                "orchestration/bin/update-state.py",
                "approval",
                "--decision",
                "approved",
                "--approver",
                "Human Product Owner",
                "--scope",
                "Advance smoke phase",
                "--reason",
                "Smoke test phase gate approval.",
                "--evidence",
                "policy audit pass",
            ],
            repo,
            label="record phase approval",
        )
        phase_gate_pass = run(
            [
                sys.executable,
                "orchestration/bin/phase-gate.py",
                "--advance-to",
                "Configured Phase 2",
                "--write-report",
                "--json",
                "--strict",
            ],
            repo,
            label="phase gate advances",
        )
        phase_gate_pass_json = json.loads(phase_gate_pass.stdout)
        assert_equal(phase_gate_pass_json["verdict"], "PASS", "phase gate pass verdict")
        state = load_state(repo)
        assert_equal(state["current_phase"], "Configured Phase 2", "phase should advance")
        assert_equal(state["phase_gate"]["last_decision"], "PASS", "phase gate state decision")

        run(
            [sys.executable, "orchestration/bin/health-check.py", "--write-report", "--summary"],
            repo,
            label="health check",
        )
        run(
            [sys.executable, "orchestration/bin/acceptance-audit.py", "--write-report"],
            repo,
            label="acceptance audit",
        )
        run(
            [sys.executable, "orchestration/bin/sync-state-doc.py", "--write-report", "--json"],
            repo,
            label="sync state doc",
        )
        assert_file(repo, "docs/project-roadmap-state.md")
        run(
            [sys.executable, "orchestration/bin/sync-state-doc.py", "--check"],
            repo,
            label="check state doc",
        )
        run(
            ["bash", "orchestration/bin/run-cycle.sh", "--roles", "docs", "--sync-state-doc"],
            repo,
            label="run cycle with state doc sync",
        )
        run(
            [sys.executable, "orchestration/bin/sync-state-doc.py", "--check"],
            repo,
            label="check state doc after cycle sync",
        )
        run(
            [sys.executable, "orchestration/bin/status.py", "--write-report", "--json", "--events", "3"],
            repo,
            label="operator status",
        )
        dashboard = run(
            [sys.executable, "orchestration/bin/operating-dashboard.py", "--write-report", "--json", "--events", "3"],
            repo,
            label="operating dashboard",
        )
        dashboard_json = json.loads(dashboard.stdout)
        assert_equal(dashboard_json["status"], "PASS", "dashboard status")
        assert_file(repo, "orchestration/operating-dashboard.md")
        dashboard_text = (repo / "orchestration" / "operating-dashboard.md").read_text()
        assert_true("## Gates" in dashboard_text, "dashboard should include gates section")
        assert_true("## Eval Status" in dashboard_text, "dashboard should include eval section")
        assert_true("## Open Blockers" in dashboard_text, "dashboard should include blockers section")
        run(
            [sys.executable, "orchestration/bin/operating-dashboard.py", "--check", "--json", "--events", "3"],
            repo,
            label="operating dashboard check",
        )
        ops_check = run(
            [sys.executable, "orchestration/bin/ops-check.py", "--json", "--strict", "--events", "3"],
            repo,
            label="ops check",
        )
        ops_check_json = json.loads(ops_check.stdout)
        assert_equal(ops_check_json["verdict"], "PASS", "ops check verdict")
        handoff = run(
            [sys.executable, "orchestration/bin/handoff-packet.py", "--role", "qa", "--write", "--write-report", "--json"],
            repo,
            label="handoff packet",
        )
        handoff_json = json.loads(handoff.stdout)
        assert_true(Path(handoff_json["path"]).exists(), "handoff packet file should exist")

        state = load_state(repo)
        assert_equal(state["health_check"]["last_decision"], "PASS", "health check decision")
        assert_equal(state["acceptance_audit"]["last_decision"], "PASS", "acceptance audit decision")
        assert_equal(state["state_doc"]["status"], "synced", "state doc status")
        assert_equal(state["operating_dashboard"]["status"], "synced", "dashboard sync status")
        assert_equal(state["ops_check"]["last_decision"], "PASS", "ops check decision")
        assert_equal(state["operator_status"]["last_decision"], "CONTINUE", "operator status decision")
        assert_true(state.get("handoff_packets"), "handoff packets should be recorded")
        assert_true(state.get("structured_reports"), "structured reports should be recorded")

        approval_request = run(
            [
                sys.executable,
                "orchestration/bin/approval-request.py",
                "--scope",
                "Synthetic approval request",
                "--reason",
                "Smoke test requires a human decision artifact.",
                "--evidence",
                "reports/json/smoke.json",
                "--risk",
                "Synthetic approval risk",
                "--recommendation",
                "Approve synthetic request after verifying smoke evidence.",
                "--open-blocker",
                "--json",
            ],
            repo,
            label="approval request",
        )
        approval_request_json = json.loads(approval_request.stdout)
        assert_true(Path(approval_request_json["markdown"]).exists(), "approval request markdown should exist")
        state = load_state(repo)
        assert_true(state.get("approval_requests"), "approval requests should be recorded")
        approval_blocker_id = state["open_blockers"][0]["id"]
        run(
            [
                sys.executable,
                "orchestration/bin/update-state.py",
                "approval",
                "--decision",
                "approved",
                "--approver",
                "Human Product Owner",
                "--scope",
                "Synthetic approval request",
                "--reason",
                "Smoke approval granted.",
                "--evidence",
                state["last_approval_request"],
            ],
            repo,
            label="record approval",
        )
        run(
            [
                sys.executable,
                "orchestration/bin/update-state.py",
                "resolve-blocker",
                approval_blocker_id,
                "--evidence",
                "Smoke approval recorded.",
            ],
            repo,
            label="resolve approval blocker",
        )
        state = load_state(repo)
        assert_true(state.get("human_approvals"), "human approval should be recorded")

        stop_report = run(
            [
                sys.executable,
                "orchestration/bin/stop-report.py",
                "--stop-reason",
                "Synthetic stop condition",
                "--file",
                "src/example.py",
                "--what-changed",
                "Smoke test created a stop report.",
                "--what-failed",
                "Synthetic stop condition needs human review.",
                "--test",
                "pytest smoke",
                "--risk",
                "Synthetic risk",
                "--recommended-next-action",
                "Resolve synthetic stop report blocker.",
                "--open-blocker",
                "--json",
            ],
            repo,
            label="stop report",
        )
        stop_json = json.loads(stop_report.stdout)
        assert_true(Path(stop_json["markdown"]).exists(), "stop report markdown should exist")
        state = load_state(repo)
        assert_true(state.get("stop_reports"), "stop reports should be recorded")
        assert_true(state.get("open_blockers"), "stop report should open a blocker")
        stop_blocker_id = state["open_blockers"][0]["id"]
        run(
            [
                sys.executable,
                "orchestration/bin/update-state.py",
                "resolve-blocker",
                stop_blocker_id,
                "--evidence",
                "Synthetic stop report blocker resolved.",
            ],
            repo,
            label="resolve stop report blocker",
        )

        run(
            [
                sys.executable,
                "orchestration/bin/update-state.py",
                "add-blocker",
                "Synthetic smoke blocker",
                "--severity",
                "high",
                "--owner",
                "smoke-test",
                "--evidence",
                "smoke-test",
            ],
            repo,
            label="add blocker",
        )
        status_with_blocker = run(
            [sys.executable, "orchestration/bin/status.py", "--json", "--strict", "--events", "0"],
            repo,
            expect=1,
            label="strict status with blocker",
        )
        status_json = json.loads(status_with_blocker.stdout)
        assert_equal(status_json["operating_decision"], "REMEDIATE", "blocker status decision")
        assert_equal(status_json["blockers"]["count"], 1, "blocker count")

        state = load_state(repo)
        blocker_id = state["open_blockers"][0]["id"]
        run(
            [
                sys.executable,
                "orchestration/bin/update-state.py",
                "resolve-blocker",
                blocker_id,
                "--evidence",
                "Smoke blocker resolved.",
            ],
            repo,
            label="resolve blocker",
        )
        run(
            [sys.executable, "orchestration/bin/status.py", "--json", "--strict", "--events", "0"],
            repo,
            label="strict status after blocker resolution",
        )

        passed = True
        return temp_root
    except Exception:
        if not keep:
            print(f"Smoke test failed. Repro directory kept at: {temp_root}", file=sys.stderr)
        raise
    finally:
        if passed and not keep:
            shutil.rmtree(temp_root, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="Keep the temporary repo for inspection.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    temp_root = smoke_test(args.keep)
    if args.keep:
        print(f"Smoke test passed. Temp root: {temp_root}")
    else:
        print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
