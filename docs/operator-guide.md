# Multi-Agent Orchestration Operator Guide

This skill creates a reusable engineering-control harness for long-running AI-assisted software work. It is designed to coordinate multiple AI loops without allowing them to race each other or make unapproved product decisions.

Core invariant: only one loop writes production code at a time. Builder owns production-code edits by default. QA, Security, Eval, Architect, Watchdog, Documentation, and subagents are reviewers or coordinators unless a human explicitly authorizes otherwise.

## What This Installs

The runtime harness creates an `orchestration/` folder in a target repo with:

- shared state in `orchestration/state.json`
- synced human-readable roadmap state at the configured `state_file_path`
- handoff packets under `orchestration/handoffs/`
- formal stop reports under `orchestration/reports/`
- human approval requests under `orchestration/approvals/requests/`
- project-local operator guide in `orchestration/README.md`
- prompt runners for Builder, QA, Security, Eval Builder, Eval, Watchdog, Architect, Docs, and Remediation
- daemon and one-cycle runners
- health check and operator status commands
- first-time project configuration command
- CI watcher
- release gate
- risk-bucket decision gate
- resume planner
- file-change guard
- Watchdog evidence preparation
- report normalizer
- read-only subagent dispatcher
- schemas for state, reports, blockers, and approvals

The harness is a local control plane. It does not replace CI, branch protection, code review, deployment gates, security review, or human product approval.

## Validate This Skill Package

Before sharing a changed copy of the skill, run:

```bash
python3 scripts/smoke_test_runtime_harness.py
```

This creates a temporary git repo, installs the harness, runs `health-check.py`, `acceptance-audit.py`, and `status.py`, verifies state records, creates a synthetic blocker, confirms strict status stops with remediation, resolves the blocker, and confirms strict status recovers.

## Install The Harness Into A Repo

From the skill folder:

```bash
python3 scripts/create_runtime_harness.py \
  --target /path/to/repo \
  --project-name "PROJECT" \
  --repo-name "REPO" \
  --roadmap-name "ROADMAP" \
  --current-phase "PHASE" \
  --current-objective "OBJECTIVE" \
  --state-file-path "docs/project-roadmap-state.md" \
  --test-command "TEST COMMAND"
```

For the one-command adoption path, use:

```bash
python3 scripts/adopt_project.py \
  --target /path/to/repo \
  --project-name "PROJECT" \
  --repo-name "REPO" \
  --roadmap-name "ROADMAP" \
  --current-phase "PHASE" \
  --current-objective "OBJECTIVE" \
  --preserved-component "COMPONENT" \
  --forbidden-change "FORBIDDEN CHANGE" \
  --test-command "TEST COMMAND"
```

`adopt_project.py` installs the runtime harness, applies first-time setup intake, runs the consolidated ops check, writes operator status, and creates the first Builder handoff packet. Use `--strict-readiness` only when the repo already has QA, Eval, Watchdog, Architect, CI, and human-approval evidence required for a passing gate.

Run this from the target repo after install:

```bash
python3 orchestration/bin/setup-intake.py
```

For automation or repeatable setup, use the non-interactive form:

```bash
python3 orchestration/bin/configure-project.py \
  --project-name "PROJECT" \
  --repo-name "REPO" \
  --roadmap-name "ROADMAP" \
  --current-phase "PHASE" \
  --current-objective "OBJECTIVE" \
  --preserved-component "COMPONENT" \
  --forbidden-change "FORBIDDEN CHANGE" \
  --sync-state-doc
python3 orchestration/bin/health-check.py --write-report
python3 orchestration/bin/acceptance-audit.py --write-report
python3 orchestration/bin/sync-state-doc.py --write-report
python3 orchestration/bin/status.py --write-report
python3 orchestration/bin/ops-check.py --strict
python3 orchestration/bin/doctor.py --write-report
python3 orchestration/bin/requirements-matrix.py --write-report --strict
python3 orchestration/bin/handoff-packet.py --write --write-report
```

`setup-intake.py` asks only for safety-relevant setup choices: project identity, current phase/objective, allowed and forbidden files, preserved components, forbidden changes, high-risk areas, eval fixtures, blocker-handling mode, agent provider, decision-risk policy, human approval policy, and operating-policy profile. Use `--apply --run-ops-check` when you want it to configure the repo and immediately verify readiness.

Expected result for a clean first setup:

- health check: `PASS`
- acceptance audit: `PASS`
- shared project state markdown exists
- operator status: `CONTINUE`
- ops check: `PASS`
- doctor returns the next exact command
- requirements matrix: `PASS`
- current role: `builder`
- open blockers: `0`

## First Invocation In Codex Or ChatGPT

Use this shape:

```text
Use the multi-agent-orchestration skill to set up orchestration for this project.
Project name: Policy QA Demo
Roadmap name: Policy Validation Stabilization Roadmap
Current phase: Phase 1 stabilization
Current objective: Prevent false-positive contradictions from weak or wrong-domain reference matches.
Preserved components:
- document parsing
- embedding retrieval
- model-based review
- keyword/token retrieval
- deterministic rules
- raw reference-section retrieval
Forbidden changes:
- Do not remove document parsing
- Do not remove embeddings
- Do not remove model-based review
- Do not migrate DB schema in Phase 1
- Do not build a knowledge graph
- Do not rewrite extraction in Phase 1
Test command: pytest tests/test_policy_validation.py
State file path: docs/project-roadmap-state.md
```

The skill should ask only setup questions that materially affect safety:

1. project and repo
2. roadmap/objective
3. current phase
4. package only or install runtime harness
5. test command and CI/PR check source
6. preserved components and forbidden changes
7. blocker-handling policy
8. agent runtime preference: `auto`, `codex-cli`, `claude-code`, `prompt-only`, or `custom-command`
9. decision policy: low risk autonomous, medium risk research-first, high risk human-required

Missing values should become `TBD` placeholders unless the repo, objective, or approval boundary is too ambiguous to proceed safely.

Use `configure-project.py` after install or whenever project boundaries change. It updates `state.json`, `operating-policy.json`, write-lock file scopes, phase gate, blocker policy, preserved components, forbidden changes, high-risk areas, eval fixtures, and the synced roadmap state file without hand-editing JSON.

For stricter autonomous operation, declare gate defaults once in `orchestration/operating-policy.json`:

```bash
python3 orchestration/bin/configure-project.py \
  --policy-profile strict-pr \
  --policy-require-latest-eval-pass true \
  --policy-require-ci-pass true \
  --policy-require-human-approval true \
  --policy-strict-gates true \
  --policy-release-gate true \
  --policy-release-mode pr
```

Scripts still accept explicit flags. Policy defaults are additive so operators can turn stronger gates on per repo without changing every command.

Audit the active policy and missing evidence:

```bash
python3 orchestration/bin/policy-audit.py --write-report --strict
```

Generate the human operating dashboard:

```bash
python3 orchestration/bin/operating-dashboard.py --write-report
```

Run the consolidated operating-system readiness check before PR creation, merge, release, or resuming a paused loop:

```bash
python3 orchestration/bin/ops-check.py --strict
```

`ops-check.py` runs health, policy audit, phase gate, release gate, operator status, state-doc sync, and dashboard generation as one report. Add `--include-acceptance-audit` when validating the harness contract itself.

Use `eval-fixture.py` when Eval Builder is authorized to turn a known behavior risk into a reusable regression artifact:

```bash
python3 orchestration/bin/eval-fixture.py create \
  --name "Wrong-domain policy match stays non-contradictory" \
  --description "Protects against false positive contradiction verdicts from weak policy evidence." \
  --input "Procedure mentions annual review; policy evidence comes from unrelated credentialing section." \
  --expected "Do not classify as contradiction without same-domain policy evidence" \
  --tolerance "May return needs-review when evidence is insufficient" \
  --risk "false positive user-facing verdict" \
  --tag "phase-1,policy-validation" \
  --write-report
```

Use `eval-result.py` when Eval Monitor runs that fixture. Non-`PASS` results should normally open a blocker:

```bash
python3 orchestration/bin/eval-result.py record \
  --fixture "evals/fixtures/wrong-domain-policy-match.json" \
  --verdict DRIFT \
  --actual '{"classification":"contradiction"}' \
  --diff "Actual classification contradicted expected non-contradiction behavior" \
  --risk "false positive user-facing verdict" \
  --recommended-next-action "Builder fixes evidence-domain filtering, then Eval Monitor reruns" \
  --open-blocker \
  --write-report
```

## Normal Operating Loop

Use one step at a time while bringing up a repo:

```bash
bash orchestration/bin/orchestration-daemon.sh --resume-plan --sync-state-doc --max-steps 1
python3 orchestration/bin/status.py --write-report
python3 orchestration/bin/handoff-packet.py --write --write-report
```

Default sequence:

```text
Builder -> QA -> Security -> Eval Builder -> Eval -> Watchdog -> Architect -> Docs
```

The expected human workflow is:

1. Builder implements the authorized phase.
2. QA checks correctness, scope, regression risk, and test coverage.
3. Security/Privacy reviews when touched areas require it.
4. Eval Builder proposes or updates behavior-level evals when authorized.
5. Eval runs behavior regression checks.
6. Watchdog audits product quality, eval quality, and process integrity.
7. Architect decides whether the phase may advance.
8. Phase gate verifies blockers, QA, Security when required, Eval, Watchdog, Architect, policy audit, and human approval.
9. Human Product Owner approves high-impact decisions.
10. Documentation updates the shared project state.
11. Builder continues only after the next assignment is authorized.

## Agent Adapter

By default, runners call `orchestration/bin/agent-adapter.py` in `auto` mode. The adapter uses Codex CLI when `codex` is installed, Claude Code when `claude` is installed, and `prompt-only` when neither runtime is available. Provider defaults live in `orchestration/agent-adapter.json`.

To override automatic provider selection, set `AGENT_PROVIDER`, set `AGENT_COMMAND`, or pass `--agent-command` through `run-cycle.py`:

```bash
AGENT_PROVIDER=codex-cli bash orchestration/bin/run-builder.sh
AGENT_PROVIDER=claude-code bash orchestration/bin/run-builder.sh
AGENT_PROVIDER=prompt-only bash orchestration/bin/run-builder.sh
AGENT_COMMAND="codex exec" bash orchestration/bin/run-builder.sh
```

You can test provider resolution directly without launching a loop:

```bash
python3 orchestration/bin/agent-adapter.py \
  --role smoke \
  --prompt-file orchestration/README.md \
  --provider auto \
  --resolve-only \
  --json
```

Configure a named provider preset without hand-editing JSON:

```bash
python3 orchestration/bin/configure-agent-provider.py --list
python3 orchestration/bin/configure-agent-provider.py --provider auto
python3 orchestration/bin/configure-agent-provider.py --provider codex-cli --command "codex exec" --test
python3 orchestration/bin/configure-agent-provider.py --provider claude-code --command "claude -p" --test
python3 orchestration/bin/configure-agent-provider.py --provider custom-command --command "your-agent-command" --test
```

Available presets are `auto`, `prompt-only`, `command`, `codex-cli`, `claude-code`, `codex-subagent`, and `custom-command`. `codex-subagent` is intentionally prompt-only unless you configure a local command bridge.

## Doctor

Use `doctor.py` when you want one operator-facing answer:

```bash
python3 orchestration/bin/doctor.py --write-report
```

The doctor checks harness health, provider configuration, operator status, resume plan, blockers, and the last ops-check result. It writes a structured report and records the next exact command in `state.json`.

## Requirements Matrix

Run the requirement matrix before treating the orchestration system as complete:

```bash
python3 orchestration/bin/requirements-matrix.py --write-report --strict
```

The matrix maps the operating-system requirements to concrete evidence: runtime files, state fields, loop runners, gates, blocker recovery, eval tooling, Watchdog, provider adapter, doctor, handoff workflow, and docs.

For full cycles:

```bash
bash orchestration/bin/run-cycle.sh \
  --roles builder,qa,security,eval-builder,eval,watchdog,architect,docs \
  --agent-command "codex exec" \
  --sync-state-doc
```

Use provider-specific commands only at the adapter edge. Keep `state.json`, reports, gates, blocker handling, and role prompts provider-neutral.

## Blockers And Remediation

Any loop should stop and report when it finds:

- repeated test failure
- blocked CI
- branch protection or review blockage
- unclear requirements
- unexpected schema migration need
- security/privacy risk
- sensitive data exposure risk
- preserved-component removal pressure
- API compatibility risk
- multiple loops editing the same production files
- product judgment that needs a human

Use structured blocker commands:

```bash
python3 orchestration/bin/update-state.py add-blocker "QA found missing regression coverage" --severity high --owner qa
python3 orchestration/bin/status.py --strict
python3 orchestration/bin/resume-plan.py --apply --prefer-remediation --write-report
bash orchestration/bin/run-remediation.sh
```

Resolve only with evidence:

```bash
python3 orchestration/bin/update-state.py resolve-blocker blocker-20260629T120000000000Z --evidence "Regression fixture added and Eval Monitor passed"
```

When a loop hits a stop condition, create a formal stop report:

```bash
python3 orchestration/bin/stop-report.py \
  --stop-reason "Schema migration unexpectedly required" \
  --file "backend/models.py" \
  --what-changed "Builder discovered implementation requires schema change" \
  --what-failed "Current phase forbids schema migration" \
  --risk "Phase scope and deployment safety" \
  --recommended-next-action "Architect and Human Product Owner decision required" \
  --open-blocker
```

The stop report follows the required format: stop reason, current phase, files involved, what changed, what failed, tests run, risks, recommended next action, and human decision needed.

## Watchdog And Eval Quality

Watchdog is the process-quality governor. It should check:

- whether the built work matches the current objective
- whether the implementation is scoped to the authorized phase
- whether evals test behavior, not just code paths
- whether Eval Builder recorded the right eval fixtures for known behavior risks
- whether preserved components stayed intact
- whether outputs, classifications, counts, or confidence changed unexpectedly
- whether reviewer loops followed their no-production-code rules
- whether release/merge needs human approval

Watchdog can recommend `PASS`, `REQUEST_FIXES`, or `STOP`. It should not make final high-impact product decisions.

Before Watchdog runs, the harness prepares a connected evidence packet:

```bash
python3 orchestration/bin/prepare-watchdog-evidence.py --write-report
```

`run-watchdog.sh` runs this automatically and includes the report path in the Watchdog prompt. The packet records the active test command, eval fixtures/results, latest role reports, PR diff/status evidence, and `orchestration/evals/rubrics/project-quality-rubric.md`. If any of these are missing, Watchdog should return `REQUEST_FIXES` or `STOP`, not `PASS`.

## Risk Decision Buckets

Use `decision-gate.py` before actions that require judgment:

```bash
python3 orchestration/bin/decision-gate.py --risk low --decision "Refresh generated reports" --evidence "reports/json/example.json"
python3 orchestration/bin/decision-gate.py --risk medium --decision "Adjust current-phase matching logic" --research-summary "Compared options and no external behavior contract changes." --confidence 0.85 --evidence "reports/json/qa.json"
python3 orchestration/bin/decision-gate.py --risk high --decision "Change user-facing classification semantics" --evidence "reports/json/watchdog.json" --open-blocker
```

Low risk: system acts and records evidence. Medium risk: system researches, records rationale/confidence, then decides whether to continue or involve a human. High risk: human approval is required before action.

Eval fixture artifacts live under:

```text
orchestration/evals/fixtures/
orchestration/evals/results/
```

Eval Monitor should report which fixture ids were run, expected vs actual behavior, and any drift that affects user-visible classifications, counts, confidence, extracted fields, or decisions.

## File Guard

The file guard is a process-drift detector, not an operating-system sandbox. It snapshots files before each role, checks what changed afterward, records violations, and can open blockers when a read-only role or subagent changes files it should not touch. It helps stop unsafe handoffs, but it does not replace branch protection, CI, code review, or filesystem permissions.

## Release And PR Gates

The harness blocks PR/release actions when gates are not satisfied.

Check release readiness:

```bash
python3 orchestration/bin/release-gate.py \
  --mode merge \
  --require-ci-pass \
  --require-latest-eval-pass \
  --require-human-approval
```

Create a human approval artifact:

```bash
python3 orchestration/bin/update-state.py approval \
  --decision approved \
  --approver "Human Product Owner" \
  --scope "Merge phase PR" \
  --reason "Watchdog PASS, CI green, release gate clear"
```

Before final approval, create an approval request:

```bash
python3 orchestration/bin/approval-request.py \
  --scope "Merge phase PR" \
  --reason "Major PR requires Human Product Owner decision" \
  --evidence "reports/json/latest-release-gate.json" \
  --risk "User-facing verdicts may change" \
  --recommendation "Approve only if release gate passes" \
  --open-blocker
```

The approval request creates markdown and JSON evidence and can open a blocker so autonomous work pauses until the human decision is recorded.

For a strict PR path:

```bash
bash orchestration/bin/run-cycle.sh \
  --roles watchdog,architect,docs \
  --watch-ci \
  --ci-required \
  --release-gate \
  --release-mode pr \
  --strict-gates \
  --require-ci-pass \
  --require-latest-eval-pass \
  --require-human-approval
```

Add `--allow-git-write --push --create-pr` only when branch/PR automation is explicitly authorized.

## Resume After Interruption

Before restarting a stopped or interrupted process:

```bash
python3 orchestration/bin/status.py --write-report
python3 orchestration/bin/resume-plan.py --apply --write-report
python3 orchestration/bin/sync-state-doc.py --write-report
```

If blockers exist and bounded recovery is allowed:

```bash
python3 orchestration/bin/resume-plan.py --apply --prefer-remediation --write-report
bash orchestration/bin/run-remediation.sh
```

Do not continue Builder work until the resume plan says `CONTINUE` or the Human Product Owner authorizes the next action.

## Acceptance Audit

Run the acceptance audit after changing the harness, before sharing the skill package, and before relying on the loop in a new repo:

```bash
python3 orchestration/bin/acceptance-audit.py --write-report
python3 orchestration/bin/requirements-matrix.py --write-report --strict
```

The audit proves the orchestration system has:

- required role runners
- daemon and run-cycle controls
- health, status, resume, release, CI, report, file-guard, and subagent scripts
- Builder-owned single-writer lock
- required state fields
- required stop conditions
- Watchdog, release, CI, and human approval gates
- operator documentation for setup and handoff

If the audit fails, fix the missing capability before running autonomous loops.

## Shared State Markdown

The runtime source of truth is `orchestration/state.json`, but loops and humans also need a readable roadmap state file. Create or refresh it with:

```bash
python3 orchestration/bin/sync-state-doc.py --write-report
```

The target path comes from `state_file_path`, usually `docs/project-roadmap-state.md` or `memory/project-roadmap-state.md`. Check freshness before handoff or in CI:

```bash
python3 orchestration/bin/sync-state-doc.py --check
```

## Handoff Packets

Create a handoff packet whenever a role finishes, before starting a separate reviewer thread, or before pausing the system:

```bash
python3 orchestration/bin/handoff-packet.py --write --write-report
```

The packet includes the project objective, current phase, next authorized action, write lock, phase gate, preserved components, forbidden changes, open blockers, gate status, last results, recent reports, recent events, role rules, and blocking policy. To target a specific loop:

```bash
python3 orchestration/bin/handoff-packet.py --role watchdog --write --write-report
```

## Subagents

Use subagents as read-only specialists inside a parent loop:

```bash
bash orchestration/bin/dispatch-subagents.sh \
  --role watchdog \
  --agent-command "codex exec" \
  --open-blockers
```

Default subagent rule: inspect and report, do not edit production files. If a subagent changes repo files, file guard records process drift and can open a blocker.

## Sharing This Skill

To share with another user:

1. Send `multi-agent-orchestration.zip`.
2. They install or unpack it into their local Codex skills directory.
3. They start a new Codex session or reload skill discovery.
4. They invoke: `Use the multi-agent-orchestration skill...`

This local package is not a global Codex deployment. Each user or environment needs its own installed copy until a shared registry/distribution mechanism is used.

## Minimal Daily Operator Checklist

```bash
python3 orchestration/bin/health-check.py --write-report
python3 orchestration/bin/acceptance-audit.py --write-report
python3 orchestration/bin/sync-state-doc.py --write-report
python3 orchestration/bin/status.py --write-report
bash orchestration/bin/orchestration-daemon.sh --resume-plan --sync-state-doc --max-steps 1
python3 orchestration/bin/status.py --write-report
python3 orchestration/bin/handoff-packet.py --write --write-report
```

Stop and ask a human before merging, changing schema, changing auth/security behavior, changing user-facing classifications/verdicts, changing external model behavior, removing preserved components, or shipping to production.
