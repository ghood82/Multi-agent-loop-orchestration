---
name: multi-agent-orchestration
description: Generate a controlled multi-loop AI engineering orchestration package for software projects. Use when a user asks to set up, adapt, or document Builder, QA, Architect/Release Manager, Security/Privacy, Eval Builder, Eval/Regression, Documentation/Memory, Watchdog/Quality Governor, Blocker Remediation, CI monitoring, report normalization, read-only subagent dispatch, file-change guard enforcement, release-gate decisions, resume planning, harness health checks, acceptance audits, Human Product Owner gates, shared state, process-drift checks, write locks, subagent review policy, or a lightweight runtime harness for a repo, roadmap, phase, PR, release, long-running task, or project stabilization workflow.
---

# Multi-Agent Orchestration

Use this skill to create a copy/paste-ready orchestration setup for a software project. The setup must be project-agnostic, reusable across repos, and centered on a shared state file that keeps all AI loops aligned.

For operator install/run/resume guidance, include or reference `README.md` from this skill package when handing the skill to another user.

Core principle: only one loop should actively write production code at a time. By default, the Builder loop is the only loop authorized to edit production code. Warn against multiple loops editing the same production files at the same time.

Default workflow:

Builder implements -> QA verifies -> Security/Privacy reviews when needed -> Eval Builder proposes or updates evals when authorized -> Eval runs regression checks -> Watchdog audits product quality, eval quality, and process integrity -> Architect decides next step -> Human approves major decisions -> Documentation updates project state -> Builder continues.

Safe parallelism rule: reviewers may run in parallel after the Builder has opened a PR, but production-code edits must stay sequential. Use one Builder, multiple reviewers, one Architect, one Human approval gate, one shared state file, and one active production-code write lock.

Runtime harness principle: when the user asks to make the loop executable, create a thin project-local harness that stores state, records events, prepares role prompts, and enforces the production-code write-lock convention. Keep the harness vendor-neutral; do not hard-code a specific agent provider unless the user asks.

Watchdog principle: the Watchdog / Quality Governor is the independent final reviewer for the whole process. It checks whether the team built the right thing well, whether evals are sufficient, and whether every loop followed the agreed workflow. The Watchdog can recommend pass, request fixes, or stop, but Human Product Owner approval remains required for high-impact decisions.

## Input Handling

Ask for or infer these inputs when available. Do not block on missing values unless the repo, objective, or approval boundary is too ambiguous to produce a useful setup. Use placeholders such as `[TBD]` for missing values.

Required or strongly preferred:

- `project_name`
- `repo_name`
- `roadmap_name`
- `current_phase`
- `current_objective`
- `docs_state_file_path`

Optional:

- `preserved_components`
- `forbidden_changes`
- `allowed_files`
- `forbidden_files`
- `active_branch`
- `active_pr`
- `test_command`
- `roadmap_phases`
- `high_risk_areas`
- `human_approval_required`
- `active_writer`
- `write_lock_owner`
- `write_lock_scope`
- `authorized_phase`
- `unauthorized_phases`
- `phase_exit_requirements`
- `controlled_taxonomy`
- `eval_fixtures`
- `eval_results`
- `runtime_harness_required`
- `agent_provider`
- `agent_command`
- `decision_policy_profile`
- `ci_monitor_required`
- `ci_required_checks_only`
- `watchdog_required`
- `eval_builder_required`
- `process_drift_ledger`
- `subagent_review_policy`
- `blocking_policy`
- `blocker_handling_mode`
- `blocker_recovery_limit`

If `docs_state_file_path` is missing, recommend `memory/project-roadmap-state.md` first when the repo has a `memory/` directory; otherwise recommend `docs/project-roadmap-state.md`.

## First-Time Setup Intake

On first invocation, ask only the setup questions that materially change the orchestration. Do not turn setup into a long questionnaire. If the user does not know an answer, use `[TBD]` and continue unless the missing detail makes the setup unsafe.

Ask:

```markdown
1. What project/repo is this for?
2. What roadmap or current objective should the loops work against?
3. What is the current phase?
4. Should I generate the orchestration package only, or also install the runtime harness into this repo?
5. What validation/test command and CI/PR check source should the loops use?
6. Are there preserved components or forbidden changes?
7. How should blocking items be handled?
8. Should agent execution use automatic provider detection, Codex CLI, Claude Code, prompt-only, or a custom command?
9. Which risk decision policy should apply: low-risk autonomous, medium-risk research-first, high-risk human-required by default?
```

Use this default blocking policy unless the user chooses otherwise:

```markdown
Blocking policy: Try one bounded recovery attempt only for low-risk mechanical issues. Stop immediately for security/privacy risk, schema migration, auth changes, external model behavior, preserved-component removal, API compatibility risk, product judgment, repeated test failures, process drift, or unclear requirements. Summarize the blocker and wait for human direction.
Blocker handling mode: stop-and-ask
Blocker recovery limit: 1 low-risk mechanical recovery attempt
```

Accept these blocker-handling modes:

- `stop-and-ask`: Stop, summarize the blocker, recommend next action, and wait for human approval.
- `bounded-recovery`: Try one bounded recovery for low-risk mechanical issues, then stop if not resolved.
- `docs-only-continue`: Continue only documentation/state updates while production work remains stopped.
- `draft-pr-with-blockers`: Open or update a draft PR with blocker notes when branch/PR automation is explicitly authorized.
- `backlog-and-pause`: Create a task/backlog note and pause the loop.

## Workflow

1. Collect or infer project inputs.
2. Identify preserved components, forbidden changes, allowed files, forbidden files, high-risk areas, controlled taxonomy terms, eval fixtures, approval gates, and blocking policy.
2a. Capture the decision policy buckets: low risk can act with evidence, medium risk researches and escalates when uncertain, high risk requires human approval.
3. Produce the orchestration package using the exact output sections in "Output Format".
4. Include a write lock and phase authorization gate in the shared state file.
5. Include ready-to-copy prompts for Builder, QA, Architect/Release Manager, Security/Privacy Reviewer, Eval Builder, Eval/Regression Monitor, Documentation/Memory Keeper, and Watchdog/Quality Governor.
6. Include a QA scope-audit checklist and semantic-drift controls.
7. Include a process-drift ledger and watchdog verdict format.
8. Include the shared state file template and stop report format.
9. If the user asks for an executable/runtime harness, use `scripts/create_runtime_harness.py` to create the harness files in the target repo.
10. Include the recommended handoff sequence and next Builder assignment.
11. If asked to apply the setup to a repo, create or update the shared state file and runtime harness only after inspecting the repo and honoring local instructions.

## Output Format

Always output the orchestration package with these sections:

```markdown
# Multi-Agent Orchestration Setup
## Project Inputs
## Shared State File
## Preserved Components
## Forbidden Changes
## Loop 1: Builder
## Loop 2: QA / Verification
## Loop 3: Architect / Release Manager
## Loop 4: Security / Privacy Reviewer
## Loop 5: Eval Builder
## Loop 6: Eval / Regression Monitor
## Loop 7: Documentation / Memory Keeper
## Loop 8: Watchdog / Quality Governor
## Loop 9: Blocker Remediation
## Runtime Harness
## Human Product Owner Gate
## Handoff Workflow
## Stop Conditions
## First Setup Task
## Next Builder Assignment
```

## Shared State File Template

Include this template in the generated package. Recommend creating or updating it at `memory/project-roadmap-state.md` or `docs/project-roadmap-state.md`.

```markdown
# Project Roadmap State

Project name:
Repo:
Roadmap:
Current phase:
Current objective:
Current active branch:
Current active PR:
Active writer:
Write lock status:
Write lock owner:
Write lock scope:
Write lock allowed files:
Write lock forbidden files:
Authorized phase:
Unauthorized phases:
Next phase requires:
Allowed files:
Forbidden files:
Preserved components:
Forbidden changes:
Controlled taxonomy:
Eval fixtures:
Eval results:
Eval quality status:
Connected tests:
Quality rubrics:
Watchdog evidence:
Decision policy:
Process drift ledger:
Subagent findings:
Blocking policy:
Blocker handling mode:
Blocker recovery limit:
Known risks:
Open blockers:
Last Builder result:
Last QA result:
Last Security result:
Last Eval Builder result:
Last Eval result:
Last Watchdog verdict:
Last Remediation result:
Last Architect decision:
Last Documentation update:
Next authorized action:
Human approval required:
```

Use these defaults when values are missing:

```markdown
Active writer: Builder
Write lock status: inactive until Builder assignment
Write lock owner: Builder
Write lock scope: [current_phase]
Authorized phase: [current_phase]
Unauthorized phases: all future phases until Architect and Human Product Owner approval
Next phase requires: QA pass + Security pass when applicable + Eval pass + Architect decision + human approval for high-impact behavior
Blocking policy: Try one bounded recovery attempt only for low-risk mechanical issues; stop immediately for security/privacy risk, schema migration, auth changes, external model behavior, preserved-component removal, API compatibility risk, product judgment, repeated test failures, process drift, or unclear requirements.
Blocker handling mode: stop-and-ask
Blocker recovery limit: 1 low-risk mechanical recovery attempt
```

## Runtime Harness

When the user asks for executable long-running loop scaffolding, create a project-local harness from `assets/runtime-harness/` with `scripts/create_runtime_harness.py`.

For one-command repo adoption, use `scripts/adopt_project.py`. It copies the runtime harness into a target repo, runs `setup-intake.py --apply --run-ops-check`, writes operator status, creates a Builder handoff packet, and prints the next Builder assignment. Use `--strict-readiness` only for repos that already have enough QA, Eval, Watchdog, Architect, CI, and human-approval evidence to pass the consolidated readiness gates.

Before sharing a modified skill package, run the packaged smoke test:

```bash
python3 scripts/smoke_test_runtime_harness.py
```

The smoke test creates a temporary git repo, installs the runtime harness, runs health check, acceptance audit, operator status, blocker creation, strict status failure, blocker resolution, and strict status recovery.

Run from the skill folder:

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

One-command adoption:

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

The harness creates:

```text
orchestration/state.json
orchestration/agent-adapter.json
docs/project-roadmap-state.md or memory/project-roadmap-state.md (created by sync command when configured)
orchestration/README.md
orchestration/events.log
orchestration/tasks.md
orchestration/locks/production-code.lock
orchestration/hooks/pre-commit
orchestration/ci/write-lock-check.yml
orchestration/approvals/.gitkeep
orchestration/approvals/requests/.gitkeep
orchestration/reports/json/.gitkeep
orchestration/reports/agent-runs/.gitkeep
orchestration/worktrees/.gitkeep
orchestration/guards/.gitkeep
orchestration/schemas/state.schema.json
orchestration/schemas/report.schema.json
orchestration/schemas/blocker.schema.json
orchestration/schemas/approval.schema.json
orchestration/subagents/manifest.json
orchestration/bin/common.sh
orchestration/bin/agent-adapter.py
orchestration/bin/configure-agent-provider.py
orchestration/bin/orchestration-daemon.sh
orchestration/bin/orchestration-daemon.py
orchestration/bin/configure-project.py
orchestration/bin/update-state.py
orchestration/bin/normalize-report.py
orchestration/bin/guard-files.py
orchestration/bin/enforce-write-lock.py
orchestration/bin/install-hooks.py
orchestration/bin/write-lock.py
orchestration/bin/release-gate.py
orchestration/bin/resume-plan.py
orchestration/bin/doctor.py
orchestration/bin/requirements-matrix.py
orchestration/bin/health-check.py
orchestration/bin/status.py
orchestration/bin/acceptance-audit.py
orchestration/bin/sync-state-doc.py
orchestration/bin/handoff-packet.py
orchestration/bin/stop-report.py
orchestration/bin/approval-request.py
orchestration/bin/dispatch-subagents.sh
orchestration/bin/dispatch-subagents.py
orchestration/bin/capture-ci.sh
orchestration/bin/watch-ci.sh
orchestration/bin/watch-ci.py
orchestration/bin/create-worktree.sh
orchestration/bin/run-builder.sh
orchestration/bin/run-qa.sh
orchestration/bin/run-security.sh
orchestration/bin/run-eval-builder.sh
orchestration/bin/run-eval.sh
orchestration/bin/run-architect.sh
orchestration/bin/run-docs.sh
orchestration/bin/run-watchdog.sh
orchestration/bin/run-remediation.sh
orchestration/bin/run-cycle.sh
orchestration/bin/run-cycle.py
```

Use the harness this way:

```bash
python3 orchestration/bin/setup-intake.py
```

Enforce the production-code write lock at the git boundary. The installer wires this in automatically for git repos; install or verify it directly with:

```bash
python3 orchestration/bin/install-hooks.py          # install / refresh the pre-commit hook
python3 orchestration/bin/install-hooks.py --check  # verify only
```

The hook runs `enforce-write-lock.py`, which fails a commit that changes production code without an active, in-scope write lock (or that touches a forbidden/preserved path). Copy `orchestration/ci/write-lock-check.yml` into `.github/workflows/` for the pull-request layer.

Manage the lock with `write-lock.py` (it keeps `state.json` and the `locks/production-code.lock` mirror in sync). `run-builder.sh` acquires it for Builder automatically at the start of a Builder run:

```bash
python3 orchestration/bin/write-lock.py acquire --owner Builder   # acquire, scoped to allowed_files
python3 orchestration/bin/write-lock.py status                    # inspect + check mirror sync
python3 orchestration/bin/write-lock.py release                   # release on handoff
```

Use `setup-intake.py` for the first human-friendly setup. It asks only for safety-relevant inputs: project identity, current phase/objective, allowed and forbidden files, preserved components, forbidden changes, high-risk areas, eval fixtures, blocker-handling mode, human approval policy, and operating-policy profile. It can print a configure command, apply the setup, and run the consolidated ops check:

```bash
python3 orchestration/bin/setup-intake.py --apply --run-ops-check
```

For repeatable automation, call `configure-project.py` directly:

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
```

```bash
python3 orchestration/bin/health-check.py --write-report
```

Run the health check immediately after first setup and before starting the daemon. It verifies required harness files, directories, JSON state, schemas, subagent manifest, executable bits, git repository context, and current blocker/Watchdog/CI/release-gate status. Add `--strict --require-agent-command` when the repo should fail setup if the agent adapter is not configured:

```bash
python3 orchestration/bin/health-check.py --strict --require-agent-command --write-report
```

Check operator status before resuming or handing off:

```bash
python3 orchestration/bin/status.py --write-report
```

Use status as the human-readable control-panel view. It summarizes the current project, daemon cursor, current role, blockers, health check, Watchdog, CI, release gate, approvals, recent events, and the next recommended command. For automation, use:

```bash
python3 orchestration/bin/status.py --json --strict
```

Run the operator-facing doctor when the user asks "what now?", "is this ready?", or "why is the loop blocked?":

```bash
python3 orchestration/bin/doctor.py --write-report
```

`doctor.py` checks harness health, provider configuration, operator status, resume plan, blockers, and the last ops-check result. It writes one structured report and records the next exact command under `state.json` `doctor.next_command`.

Run the requirement matrix before claiming the orchestration operating system is complete:

```bash
python3 orchestration/bin/requirements-matrix.py --write-report --strict
```

`requirements-matrix.py` maps explicit operating-system requirements to concrete evidence in the generated runtime: files, state fields, runners, gates, blocker recovery, eval tooling, Watchdog, provider adapter, doctor, handoff workflow, and operator docs.

Run the consolidated operating-system readiness check before PR creation, merge, release, or resuming a paused loop:

```bash
python3 orchestration/bin/ops-check.py --strict
```

`ops-check.py` runs health, policy audit, phase gate, release gate, operator status, shared state sync, and operating-dashboard generation. It records one control-plane verdict in `state.json` under `ops_check`, so humans and future loops can see whether the autonomous workflow is actually ready to continue.

Create or refresh the shared human-readable project state file:

```bash
python3 orchestration/bin/sync-state-doc.py --write-report
```

Use `--check` in CI or before handoff to fail if the markdown state file is missing or stale:

```bash
python3 orchestration/bin/sync-state-doc.py --check
```

Create a handoff packet for the next role:

```bash
python3 orchestration/bin/handoff-packet.py --write --write-report
```

Create a packet for a specific loop:

```bash
python3 orchestration/bin/handoff-packet.py --role qa --write --write-report
```

Create a formal stop report when any global stop condition occurs:

```bash
python3 orchestration/bin/stop-report.py \
  --stop-reason "Security/privacy risk found" \
  --file "path/to/file.py" \
  --what-failed "Sensitive data may be logged" \
  --risk "PII exposure" \
  --recommended-next-action "Human Product Owner and Security review required" \
  --open-blocker
```

Request a Human Product Owner decision before high-impact behavior:

```bash
python3 orchestration/bin/approval-request.py \
  --scope "Merge Phase 1 PR" \
  --reason "Watchdog PASS and CI green, but merge requires human approval" \
  --evidence "reports/json/latest-watchdog.json" \
  --risk "User-facing classifications may change" \
  --recommendation "Approve merge if release gate passes" \
  --open-blocker
```

Run the acceptance audit after setup changes or before sharing the harness:

```bash
python3 orchestration/bin/acceptance-audit.py --write-report
```

The acceptance audit checks that the required loops, prompt runners, state fields, single-writer lock, blocking policy, Watchdog/release/CI/human gates, operator docs, and core control scripts are present. It is a capability audit for the orchestration system itself, not a product-code test suite.

```bash
bash orchestration/bin/run-builder.sh
bash orchestration/bin/run-qa.sh
bash orchestration/bin/run-security.sh
bash orchestration/bin/run-eval-builder.sh
bash orchestration/bin/run-eval.sh
bash orchestration/bin/run-architect.sh
bash orchestration/bin/run-docs.sh
bash orchestration/bin/run-watchdog.sh
bash orchestration/bin/run-remediation.sh
```

By default, each runner prepares a prompt in `orchestration/prompts/`, calls `orchestration/bin/agent-adapter.py` in `auto` mode, records the adapter run under `orchestration/reports/agent-runs/`, and appends JSON events to `orchestration/events.log`. `auto` uses Codex CLI when `codex` is installed, Claude Code when `claude` is installed, and `prompt-only` when neither runtime is available. Provider defaults live in `orchestration/agent-adapter.json`.

To override automatic provider selection, set `AGENT_PROVIDER` or `AGENT_COMMAND`:

```bash
AGENT_PROVIDER=codex-cli bash orchestration/bin/run-builder.sh
AGENT_PROVIDER=claude-code bash orchestration/bin/run-builder.sh
AGENT_PROVIDER=prompt-only bash orchestration/bin/run-builder.sh
AGENT_COMMAND="codex exec" bash orchestration/bin/run-builder.sh
```

Test provider resolution directly without launching an agent:

```bash
python3 orchestration/bin/agent-adapter.py \
  --role smoke \
  --prompt-file orchestration/README.md \
  --provider auto \
  --resolve-only \
  --json
```

Configure a named provider preset:

```bash
python3 orchestration/bin/configure-agent-provider.py --list
python3 orchestration/bin/configure-agent-provider.py --provider auto
python3 orchestration/bin/configure-agent-provider.py --provider codex-cli --command "codex exec" --test
python3 orchestration/bin/configure-agent-provider.py --provider claude-code --command "claude -p" --test
python3 orchestration/bin/configure-agent-provider.py --provider custom-command --command "your-agent-command" --test
```

Available presets are `auto`, `prompt-only`, `command`, `codex-cli`, `claude-code`, `codex-subagent`, and `custom-command`. Keep provider-specific details in `agent-adapter.json` and `configure-agent-provider.py`, not in role prompts or state logic.

Use the optional cycle adapter to run the role sequence and collect reports:

```bash
bash orchestration/bin/run-cycle.sh --sync-state-doc
```

Use the daemon to drive the next authorized role from `orchestration/state.json`:

```bash
bash orchestration/bin/orchestration-daemon.sh --resume-plan --sync-state-doc --max-steps 1
```

Run multiple safe steps without git writes:

```bash
bash orchestration/bin/orchestration-daemon.sh --max-steps 8
```

Run continuously with pauses between steps:

```bash
bash orchestration/bin/orchestration-daemon.sh --continuous --sleep-seconds 60
```

The daemon:

- Reads `daemon.queue` and `daemon.cursor` from `state.json`.
- Runs one role at a time through `run-cycle.sh`.
- Advances the queue only after the role succeeds.
- Pauses on open blockers by default.
- Routes non-`PASS` Watchdog verdicts to Blocker Remediation.
- Can refresh CI/PR check state before gated actions when run with `--watch-ci`.
- Can dispatch read-only specialist subagents for the current role when run with `--dispatch-subagents`.
- Can run resume planning before choosing the next role when run with `--resume-plan`.
- Records daemon activity in `events.log`.

Structured evidence files live under:

```text
orchestration/reports/json/
orchestration/approvals/
orchestration/schemas/
orchestration/operating-policy.json
```

Use schemas as the contract for machine-readable state, reports, blockers, and human approvals. The harness does not require a JSON Schema validator to run, but these files document the expected shape and can be used by CI or custom checks.

Use `operating-policy.json` to declare repo-level gate defaults once. `configure-project.py` can update the policy:

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

Policy defaults are additive with command flags. Leave gates disabled in the policy until the project has the required eval, CI, and approval evidence.

Audit the active policy and missing gate evidence:

```bash
python3 orchestration/bin/policy-audit.py --write-report --strict
```

Generate the human operating dashboard:

```bash
python3 orchestration/bin/operating-dashboard.py --write-report
```

Gate phase advancement with current evidence:

```bash
python3 orchestration/bin/phase-gate.py --write-report --strict
python3 orchestration/bin/phase-gate.py --advance-to "Phase 2" --write-report --strict
```

The cycle adapter is safe by default:

- It prepares prompts and writes role outputs under `orchestration/reports/`.
- It does not create branches, commit, push, or open PRs unless explicit flags are passed.
- It requires `--allow-git-write` before any git write action.
- It requires `--push` before `--create-pr`.
- It blocks PR creation when `orchestration/state.json` has non-empty `open_blockers`.
- It blocks PR creation unless the latest Watchdog report has an explicit `PASS` verdict, unless a human explicitly passes `--skip-watchdog-pr-check`.
- With `--strict-gates`, it also blocks commit and push when `open_blockers` is non-empty or the latest Watchdog verdict is not `PASS`.
- With `--remediate-on-gate-failure`, it prepares a Blocker Remediation prompt/report when gates fail, so the next step is a fix plan rather than a silent stop.
- With `--require-ci-pass`, strict-gated actions also require `ci_status.conclusion` to be `success`, `succeeded`, `passed`, `pass`, or `green`.
- With `--require-latest-eval-pass`, strict-gated actions also require the latest Eval Monitor result to be `PASS`.
- With `--require-human-approval`, PR creation also requires an approved artifact in `orchestration/approvals/`.
- It runs the file guard by default around each role. Builder and Remediation may write within policy; Docs may write docs/memory/markdown; QA, Security, Eval, Architect, Watchdog, and subagents are read-only for repo files.
- File guard violations are recorded in `file_guard_checks` and can open blockers automatically.
- It can run the release gate before commit, push, or PR creation with `--release-gate`.

Prepare Watchdog evidence before a final quality verdict:

```bash
python3 orchestration/bin/prepare-watchdog-evidence.py --write-report
```

`run-watchdog.sh` runs this automatically. The evidence packet records connected tests, eval fixtures/results, latest reports, PR diff/status evidence, and the project-specific quality rubric. If that packet reports missing evidence, Watchdog should not return `PASS`.

Use risk decision buckets when the system has to decide whether it can act:

```bash
python3 orchestration/bin/decision-gate.py --risk low --decision "Refresh generated reports" --evidence "reports/json/example.json"
python3 orchestration/bin/decision-gate.py --risk medium --decision "Adjust current-phase behavior" --research-summary "Compared options and no high-impact behavior changes." --confidence 0.85 --evidence "reports/json/qa.json"
python3 orchestration/bin/decision-gate.py --risk high --decision "Change user-facing classification semantics" --evidence "reports/json/watchdog.json" --open-blocker
```

Low risk means the system may act and record evidence. Medium risk means research first, then decide whether to escalate. High risk means Human Product Owner approval is required.

Use structured state commands instead of hand-editing JSON when possible:

```bash
python3 orchestration/bin/update-state.py add-blocker "QA found missing regression coverage" --severity high --owner eval-builder
python3 orchestration/bin/update-state.py resolve-blocker blocker-20260629T120000Z --evidence "Eval Builder added fixture and Eval Monitor passed"
python3 orchestration/bin/update-state.py record-report --role watchdog --status complete --verdict PASS --summary "All gates passed"
python3 orchestration/bin/update-state.py approval --decision approved --approver "Human Product Owner" --scope "Merge phase 1 PR" --reason "Watchdog PASS and CI green"
```

When Eval Builder is authorized to preserve behavior evidence, create a fixture artifact instead of leaving the eval as prose:

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

When Eval Monitor runs a fixture, record the actual-vs-expected result as an artifact. Use `--open-blocker` for `FAIL`, `DRIFT`, `BLOCKED`, or `SKIPPED` results unless Architect explicitly decides the result is informational:

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

Normalize markdown role reports into structured JSON:

```bash
python3 orchestration/bin/normalize-report.py orchestration/reports/20260629T120000Z-watchdog.md --open-blockers
```

`run-cycle.sh` normalizes generated role reports by default. Add `--open-blockers-from-reports` to open blockers for explicit negative verdicts, listed blockers, required fixes, or stop reasons. Add `--no-normalize-reports` only when debugging the harness itself.

Run the file guard directly:

```bash
snapshot="$(python3 orchestration/bin/guard-files.py snapshot --role qa)"
python3 orchestration/bin/guard-files.py check --snapshot "$snapshot" --role qa --open-blocker
```

Use `--disable-file-guard` only when debugging the harness itself. A read-only loop or subagent changing repo files should be treated as process drift and stopped.

The file guard is a process-drift detector, not an operating-system sandbox. It snapshots files before and after a role, records unauthorized changes, and can open blockers, but it does not replace filesystem permissions, CI, branch protection, or human review.

Evaluate release readiness:

```bash
python3 orchestration/bin/release-gate.py \
  --mode merge \
  --require-ci-pass \
  --require-latest-eval-pass \
  --require-human-approval
```

Use release gate inside a cycle:

```bash
bash orchestration/bin/run-cycle.sh \
  --roles watchdog,architect,docs \
  --release-gate \
  --release-mode merge \
  --require-ci-pass \
  --require-latest-eval-pass \
  --require-human-approval \
  --strict-gates
```

For local/offline adapters, pass `--pr-from-file path/to/gh-pr-view.json` to `release-gate.py` or `--release-pr-from-file path/to/gh-pr-view.json` to `run-cycle.sh`. The file should match `gh pr view --json number,url,state,isDraft,mergeable,mergeStateStatus,reviewDecision,headRefName,baseRefName`.

Plan a safe resume after interruption:

```bash
python3 orchestration/bin/resume-plan.py --apply --write-report
```

Prefer remediation instead of pausing when blockers are open:

```bash
python3 orchestration/bin/resume-plan.py --apply --prefer-remediation
```

Run the daemon with resume planning:

```bash
bash orchestration/bin/orchestration-daemon.sh \
  --sync-state-doc \
  --resume-plan \
  --max-steps 1
```

The resume planner reads `state.json`, `events.log`, daemon cursor/status, open blockers, CI, Watchdog, and release-gate state. It updates `next_authorized_action`, `resume_plan`, and the daemon cursor/status when `--apply` is used.

Dispatch read-only specialist subagents:

```bash
bash orchestration/bin/dispatch-subagents.sh \
  --role watchdog \
  --agent-command "codex exec" \
  --open-blockers
```

Run parent loops and their specialists together:

```bash
bash orchestration/bin/run-cycle.sh \
  --roles qa,security,eval,watchdog \
  --agent-command "codex exec" \
  --dispatch-subagents \
  --subagent-command "codex exec" \
  --subagent-open-blockers
```

The default subagent manifest lives at `orchestration/subagents/manifest.json`. Subagents are read-only by default and should report findings, not edit files. Their markdown reports are written under `orchestration/reports/subagents/`, normalized into `orchestration/reports/json/`, and recorded in `subagent_findings` / `subagent_runs` in `state.json`.
The dispatcher also runs the file guard around each subagent by default. If a subagent changes repo files, the dispatcher records a guard violation and opens a blocker unless explicitly told not to.

Capture CI status:

```bash
bash orchestration/bin/capture-ci.sh github success "Deploy and tests passed" "https://example.invalid/run"
```

Monitor active PR checks with GitHub CLI and write the result to `state.json`:

```bash
bash orchestration/bin/watch-ci.sh --required
```

Wait for checks to finish before recording the result:

```bash
bash orchestration/bin/watch-ci.sh --required --watch --timeout-seconds 900
```

Refresh CI inside a strict-gated cycle:

```bash
bash orchestration/bin/run-cycle.sh \
  --roles watchdog,architect,docs \
  --watch-ci \
  --ci-required \
  --ci-timeout-seconds 900 \
  --strict-gates \
  --require-ci-pass
```

For local/offline adapters, pass `--ci-from-file path/to/gh-pr-checks.json` with the same JSON array shape returned by `gh pr checks --json bucket,completedAt,description,event,link,name,startedAt,state,workflow`.

Refresh CI inside the daemon:

```bash
bash orchestration/bin/orchestration-daemon.sh \
  --max-steps 1 \
  --watch-ci \
  --ci-required \
  --require-ci-pass
```

Create an isolated git worktree for a role when a repo needs stronger file isolation:

```bash
bash orchestration/bin/create-worktree.sh builder orchestration/phase-1-builder
```

Optional GitHub PR flow:

```bash
bash orchestration/bin/run-cycle.sh \
  --roles builder,qa,security,eval-builder,eval,watchdog,architect,docs \
  --agent-command "codex exec" \
  --create-branch "orchestration/phase-1" \
  --commit-message "Run phase 1 orchestration" \
  --push \
  --create-pr \
  --pr-title "Phase 1 orchestration" \
  --watch-ci \
  --ci-required \
  --dispatch-subagents \
  --subagent-command "codex exec" \
  --release-gate \
  --release-mode pr \
  --strict-gates \
  --remediate-on-gate-failure \
  --require-ci-pass \
  --require-latest-eval-pass \
  --require-human-approval \
  --allow-git-write
```

Treat this as a lightweight local control plane, not a full autonomy platform. It does not replace CI, branch protection, PR review, security review, or human product approval.

## Subagent Usage Policy

Use subagents as specialists inside a loop, not as independent authorities. By default, subagents are read-only reviewers that inspect, reason, and report findings.

Allowed subagent patterns:

- Builder may use subagents for repo scouting, impact analysis, and test-failure diagnosis.
- QA may use subagents for bug hunting, regression review, edge-case review, test coverage review, and scope audit.
- Security may use subagents for auth, tenant isolation, sensitive logging, dependency/config, and model/API payload privacy review.
- Eval Builder may use subagents to propose eval cases and expected behavior.
- Eval may use subagents to compare expected vs actual outputs and detect drift.
- Architect may use subagents to compare reports and assess phase readiness.
- Watchdog may use subagents for product-quality review, process-integrity review, eval-quality review, security-handoff review, and regression-risk review.

Default restrictions:

- Subagents must not edit production code unless the active loop has explicit authorization and the Builder owns the production-code write lock.
- Subagents must not advance roadmap phases, merge PRs, bypass human approval, alter controlled taxonomy, or release the write lock.
- Subagents launched by `dispatch-subagents.py` are treated as read-only even when the parent loop is Builder.
- Negative subagent verdicts should become blockers when `--open-blockers`, `--subagent-open-blockers`, or strict gates are used.
- Subagent findings must be summarized into the parent loop report and, when material, recorded in the shared state file.

## Loop Templates

When generating prompts, preserve the project-specific values supplied by the user. Keep prompts self-contained so they can be pasted into separate Codex/ChatGPT threads.

### Loop 1: Builder

```markdown
You are the Builder loop for [project_name].

Roadmap: [roadmap_name]
Current phase: [current_phase]
Current objective: [current_objective]
Shared state file: [docs_state_file_path]
Active branch: [active_branch]
Active PR: [active_pr]
Write lock owner: [write_lock_owner or Builder]
Write lock scope: [write_lock_scope or current_phase]
Authorized phase: [authorized_phase or current_phase]
Unauthorized phases: [unauthorized_phases]
Allowed files: [allowed_files]
Forbidden files: [forbidden_files]
Preserved components: [preserved_components]
Forbidden changes: [forbidden_changes]
Controlled taxonomy: [controlled_taxonomy]
Test command: [test_command]

Rules:
- Read the shared state file before acting.
- Confirm the production-code write lock is assigned to Builder for the authorized phase before editing production code.
- If the write lock is active for another loop, stop without editing production code.
- Implement only the currently assigned phase.
- Do not jump ahead to future phases.
- Do not rewrite unrelated systems.
- Do not remove preserved components.
- Respect forbidden changes and forbidden files.
- Keep taxonomy terms stable. Do not redefine verdicts, reason codes, confidence meanings, coverage gates, direction values, or human-review flags without Architect and Human approval.
- Add or update tests for changed behavior.
- Run relevant tests.
- Fix failures and repeat the fix/test loop up to 5 times.
- Create or update a PR when implementation and local validation are complete.
- You are the only loop allowed to write production code by default.
- Stop if another loop is editing the same production files.

Stop if blocked by CI, branch protection, unclear requirements, schema risk, security/privacy risk, preserved-component removal, API compatibility risk, or repeated test failure.

Report:
- Summary of implementation
- Files changed
- Write lock status and scope
- Tests run and results
- PR/branch status
- Risks or blockers
- Recommended next handoff
```

### Loop 2: QA / Verification

```markdown
You are the QA / Verification loop for [project_name].

Roadmap: [roadmap_name]
Current phase: [current_phase]
Current objective: [current_objective]
Shared state file: [docs_state_file_path]
Builder branch/PR: [active_branch] / [active_pr]
Authorized phase: [authorized_phase or current_phase]
Allowed files: [allowed_files]
Forbidden files: [forbidden_files]
Preserved components: [preserved_components]
Forbidden changes: [forbidden_changes]
Controlled taxonomy: [controlled_taxonomy]
Test command: [test_command]

Rules:
- Read the shared state file and Builder report before acting.
- Review the Builder PR for correctness, scope, regressions, and test coverage.
- Perform a scope audit:
  - Did this change only the authorized phase?
  - Did it touch forbidden systems or files?
  - Did it alter preserved components?
  - Did it add schema migrations?
  - Did it change model-provider behavior?
  - Did it change API, UI, export, report, verdict, classification, or taxonomy contracts?
- Do not implement roadmap features.
- Do not refactor.
- Do not change unrelated files.
- Do not modify production code unless explicitly authorized.
- Focus on verification, scope control, tests, and regression risk.
- Suggest fixes when needed.
- Add test-only changes only if explicitly authorized.

Report:
- Verification summary
- Scope findings
- Scope audit result
- Taxonomy or semantic-drift concerns
- Regression risks
- Tests/checks run and results
- Missing coverage
- Required fixes before merge
- Recommendation: approve, request changes, or stop
```

### Loop 3: Architect / Release Manager

```markdown
You are the Architect / Release Manager loop for [project_name].

Roadmap: [roadmap_name]
Current phase: [current_phase]
Current objective: [current_objective]
Shared state file: [docs_state_file_path]
Active branch: [active_branch]
Active PR: [active_pr]
Roadmap phases: [roadmap_phases]
Human approval required: [human_approval_required]
Write lock status: [write_lock_status]
Authorized phase: [authorized_phase or current_phase]
Unauthorized phases: [unauthorized_phases]
Phase exit requirements: [phase_exit_requirements]
Controlled taxonomy: [controlled_taxonomy]

Rules:
- Read the shared state file before deciding.
- Control phase sequencing.
- Prevent architecture drift.
- Prevent semantic drift by keeping controlled taxonomy meanings stable across loops.
- Compare Builder and QA reports.
- Read Security and Eval reports when available.
- Decide whether the current phase is complete.
- Prepare the next Builder assignment.
- Do not authorize the next phase if current work is failing, blocked, unreviewed, scope-dirty, semantically inconsistent, or missing required human approval.
- Do not release the write lock to another production-code writer unless the current Builder work is complete, stopped, or explicitly reassigned.
- Do not write feature code unless explicitly instructed.

Report:
- Phase status
- Evidence considered
- Architecture risks
- Semantic-drift risks
- Release/merge readiness
- Decision: continue current phase, request fixes, seek human approval, merge/release, or start next phase
- Write lock decision
- Next Builder assignment
```

### Loop 4: Security / Privacy Reviewer

```markdown
You are the Security / Privacy Reviewer loop for [project_name].

Roadmap: [roadmap_name]
Current phase: [current_phase]
Current objective: [current_objective]
Shared state file: [docs_state_file_path]
Active branch/PR: [active_branch] / [active_pr]
High-risk areas: [high_risk_areas]
Preserved components: [preserved_components]
Forbidden changes: [forbidden_changes]
Controlled taxonomy: [controlled_taxonomy]

Use this loop especially when changes touch authentication, authorization, file uploads, documents, logs, external APIs, LLM/model calls, PII, PHI, sensitive data, database access, tenant separation, exports, or reports.

Rules:
- Read the shared state file and relevant PR diff before acting.
- Check for data exposure, sensitive information leakage, unsafe logging, auth issues, tenant leakage, risky model/API payloads, dependency risk, and unsafe defaults.
- Check whether additional agents, shared memory, logs, or handoff artifacts create sensitive-data exposure.
- Check whether model/API payload changes alter sensitive data flow or external provider behavior.
- Do not modify production code unless explicitly authorized.
- Stop if sensitive data may be exposed or product/security judgment is required.

Report:
- Security/privacy findings ordered by severity
- Files and flows reviewed
- Data exposure risks
- Auth/tenant risks
- Model/API payload risks
- Dependency/config risks
- Required fixes or approval gates
- Recommendation: approve, request changes, or stop
```

### Loop 5: Eval Builder

```markdown
You are the Eval Builder loop for [project_name].

Roadmap: [roadmap_name]
Current phase: [current_phase]
Current objective: [current_objective]
Shared state file: [docs_state_file_path]
Authorized phase: [authorized_phase or current_phase]
Controlled taxonomy: [controlled_taxonomy]
Known risks: [known_risks]
Forbidden changes: [forbidden_changes]

Rules:
- Read the shared state file, current objective, Builder plan/report, QA findings, Security findings, and prior Eval results before acting.
- Build or propose behavior-level eval cases that test purpose, not just syntax.
- Cover happy paths, known regressions, wrong-domain examples, boundary cases, ambiguous cases, and user-visible classifications or verdicts.
- Define expected outputs, acceptable tolerances, required fixtures, and repro commands.
- Do not change production code.
- Create or update eval fixtures only if explicitly authorized.
- When authorized and the runtime harness is installed, use `python3 orchestration/bin/eval-fixture.py create ...` to write the fixture and update shared state.
- Stop if expected behavior requires product judgment, taxonomy changes, sensitive data, or schema changes.

Report:
- Eval cases proposed or updated
- Behavior protected by each case
- Expected outputs and tolerances
- Fixtures/files touched
- Gaps that still need human or Architect decision
- Recommendation: ready for Eval Monitor, request clarification, or stop
```

### Loop 6: Eval / Regression Monitor

```markdown
You are the Eval / Regression Monitor loop for [project_name].

Roadmap: [roadmap_name]
Current phase: [current_phase]
Current objective: [current_objective]
Shared state file: [docs_state_file_path]
Eval fixtures or examples: [eval_fixtures or TBD]
Test command: [test_command]
Controlled taxonomy: [controlled_taxonomy]

Rules:
- Read the shared state file before acting.
- Measure behavior over known examples and detect drift.
- Check behavior-level outputs, not only unit tests.
- Track expected vs actual behavior.
- Report changed classifications, confidence, counts, ranking, extracted fields, or user-visible outputs.
- Include known edge cases for wrong-domain matches, silent coverage, vague evidence, ambiguous classifications, extraction fragments, and any project-specific high-risk outputs.
- Flag semantic drift when the same term is used with a new meaning.
- When the runtime harness is installed, use `python3 orchestration/bin/eval-result.py record ...` to preserve expected-vs-actual evidence.
- Open a blocker for failed, drifted, blocked, or skipped required evals unless Architect explicitly marks the result informational.
- Do not change production code unless explicitly authorized.
- Do not create or update eval fixtures unless Eval Builder or Architect explicitly authorized it.

Report:
- Eval set used
- Expected vs actual behavior
- Behavioral diffs
- Regression risks
- Repro commands
- Recommendation: pass, investigate, request Builder fixes, or stop
```

### Loop 7: Documentation / Memory Keeper

```markdown
You are the Documentation / Memory Keeper loop for [project_name].

Roadmap: [roadmap_name]
Current phase: [current_phase]
Current objective: [current_objective]
Shared state file: [docs_state_file_path]
Active branch/PR: [active_branch] / [active_pr]
Write lock status: [write_lock_status]
Authorized phase: [authorized_phase or current_phase]
Controlled taxonomy: [controlled_taxonomy]

Rules:
- Read Builder, QA, Architect, Security, Eval Builder, Eval Monitor, Watchdog, and subagent reports before updating docs.
- Update the shared project state.
- Update roadmap docs when authorized.
- Record write lock status, authorized phase, unauthorized phases, decisions, risks, blockers, phase status, PR status, test status, eval-builder status, eval status, watchdog verdict, process-drift findings, security status, and next authorized action.
- Record controlled taxonomy meanings when they are part of the project behavior.
- Do not write production code.
- Do not change product logic.
- Do not mark a phase complete unless Architect or Human Product Owner has authorized it.

Report:
- Documentation updates made
- State file changes
- Decisions recorded
- Remaining documentation gaps
- Next authorized action
```

### Loop 8: Watchdog / Quality Governor

```markdown
You are the Watchdog / Quality Governor loop for [project_name].

Roadmap: [roadmap_name]
Current phase: [current_phase]
Current objective: [current_objective]
Shared state file: [docs_state_file_path]
Active branch/PR: [active_branch] / [active_pr]
Authorized phase: [authorized_phase or current_phase]
Write lock status: [write_lock_status]
Preserved components: [preserved_components]
Forbidden changes: [forbidden_changes]
Controlled taxonomy: [controlled_taxonomy]
Eval fixtures: [eval_fixtures]
Eval results: [eval_results]
Watchdog evidence packet: [watchdog_evidence.last_report]
Decision policy: [decision_policy]
Human approval required: [human_approval_required]

Mission:
- Decide whether the work is purposeful, high-quality, and process-compliant.
- Audit product quality, eval quality, process integrity, and handoff completeness.
- Read the prepared Watchdog evidence packet first. If connected tests, eval fixtures, eval results, PR diff evidence, reports, or the project quality rubric are missing, do not return `PASS`.
- Use subagents as read-only specialist reviewers when useful, then synthesize their findings.

Product quality checks:
- Did the change solve the assigned objective, not merely add code?
- Is the implementation maintainable, scoped, and consistent with existing architecture?
- Are edge cases, failure modes, and regressions considered?
- Are tests meaningful for the changed behavior?
- Are preserved components intact and forbidden changes avoided?

Eval quality checks:
- Did Eval Builder create or propose the right behavior examples?
- Do evals cover purpose, known regressions, boundary cases, and user-visible outcomes?
- Did Eval Monitor actually run the evals and report expected vs actual behavior?
- Were failures, drift, or missing coverage handled instead of waved through?

Process integrity checks:
- Did Builder hold the production-code write lock before editing production code?
- Did each loop stay in its role?
- Did any read-only loop or subagent edit production code?
- Did the PR stay inside the authorized phase and allowed files?
- Were QA, Security, Eval Builder, Eval Monitor, Architect, Documentation, and human gates completed when required?
- Does the shared state match the PR diff, reports, and event log?

Verdict:
- `PASS`: work is scoped, purposeful, verified, and process-compliant.
- `REQUEST_FIXES`: specific fixes are required before Architect/Human approval.
- `PROCESS_WARNING`: workflow drift exists but may be corrected without stopping.
- `STOP`: product judgment, security/privacy risk, eval insufficiency, process failure, or human approval is required.

Report:
- Watchdog verdict
- Product quality findings
- Eval quality findings
- Process drift findings
- Subagent findings summarized
- Evidence checked
- Required fixes
- Human decision needed
- Recommended next action
```

### Loop 9: Blocker Remediation

```markdown
You are the Blocker Remediation loop for [project_name].

Roadmap: [roadmap_name]
Current phase: [current_phase]
Current objective: [current_objective]
Shared state file: [docs_state_file_path]
Active branch/PR: [active_branch] / [active_pr]
Open blockers: [open_blockers]
Latest Watchdog verdict: [last_watchdog_verdict]
Blocking policy: [blocking_policy]

Mission:
- Convert open blockers or non-PASS Watchdog findings into a concrete remediation plan.
- Classify each blocker as low-risk mechanical, Builder fix required, QA/Security/Eval follow-up required, Docs-only correction, or Human Product Owner decision required.
- Route each item to the correct owner/loop.
- Keep production-code fixes under the Builder write lock.

Rules:
- Do not edit production code.
- Do not clear blockers unless there is direct evidence they are resolved.
- Do not authorize phase advancement, merge, release, or PR creation.
- For low-risk mechanical blockers, recommend one bounded recovery attempt and exact commands.
- For production-code defects, assign remediation back to Builder with required tests.
- For eval gaps, assign Eval Builder and Eval Monitor follow-up.
- For security/privacy/auth/schema/model-behavior/product-judgment blockers, stop and request human direction.
- For process drift, identify the broken rule, responsible loop, required correction, and whether Watchdog must rerun.

Report:
- Remediation summary
- Blocker classification
- Required owner/loop for each blocker
- Specific fix or follow-up command
- Tests/evals/reviews required after fix
- Whether Watchdog must rerun
- Whether human decision is needed
- Next authorized action
```

## Human Product Owner Gate

Include this gate in every generated package:

```markdown
AI loops can recommend. They should not make final product decisions on high-impact behavior.

Human approval is required before:
- Merging major PRs
- Starting a high-risk phase
- Adding schema migrations
- Changing external model behavior
- Changing auth/security behavior
- Changing user-facing verdicts or classifications
- Changing controlled taxonomy meanings
- Removing preserved components
- Shipping to production
```

## Stop Conditions

Apply these global stop conditions to all loops:

- Tests fail after repeated fixes.
- CI is blocked.
- Branch protection blocks merge.
- Requirements are unclear.
- A schema migration is unexpectedly needed.
- Security/privacy risk is found.
- Sensitive data may be exposed.
- Preserved components would need to be removed.
- API compatibility may break.
- Multiple loops are editing the same production files.
- A write lock is active for another loop.
- A PR fails the scope audit.
- Semantic drift is detected in controlled taxonomy.
- Eval coverage is missing for behavior that the phase claims to protect.
- Eval Monitor did not actually run required evals.
- Watchdog returns `REQUEST_FIXES`, `PROCESS_WARNING`, or `STOP`.
- Process drift is detected, including skipped gates, stale state, unauthorized edits, subagents editing production code, or mismatch between state and PR diff.
- Product judgment is required.

Apply the configured blocking policy when any stop condition occurs. Default behavior is `stop-and-ask`: stop the loop, write a blocker report, recommend a next action, and wait for human direction. Use bounded recovery only for low-risk mechanical issues and only up to the configured recovery limit.

Use this stop report format:

```markdown
Stop reason:
Blocking policy:
Blocker handling mode:
Recovery attempts used:
Current phase:
Files involved:
What changed:
What failed:
Tests run:
Risks:
Process drift findings:
Watchdog verdict:
Recommended next action:
Human decision needed:
```

## Handoff Workflow

Generate a handoff sequence like this, adapting details to the project:

1. Documentation creates or updates the shared state file.
2. Architect assigns the current phase and allowed scope.
3. Architect sets the write lock owner, write lock scope, authorized phase, unauthorized phases, and phase exit requirements.
4. Builder implements only the assigned objective and reports test evidence.
5. QA verifies correctness, scope, regressions, coverage, and scope-audit status.
6. Security reviews if the change touches high-risk areas.
7. Eval Builder proposes or updates behavior-level evals when the phase needs new coverage.
8. Eval Monitor runs behavior-level regression checks and flags semantic drift.
9. Watchdog audits product quality, eval quality, and process integrity.
10. If blockers are open or Watchdog is not `PASS`, Blocker Remediation classifies issues and routes them to Builder, QA, Security, Eval Builder, Eval Monitor, Documentation, Architect, or Human Product Owner.
11. Assigned loops resolve the remediation items within their authority.
12. Watchdog reruns after remediation and must return `PASS` before strict commit/push/PR gates proceed.
13. Architect compares reports and decides the next safe action.
14. Phase gate blocks phase advancement unless blockers, QA, Security when required, Eval, Watchdog, Architect, policy audit, and human approval conditions are satisfied.
15. Human Product Owner approves high-impact decisions.
16. Documentation records the decision, state, write lock status, process-drift findings, watchdog verdict, remediation status, risks, and next authorized action.
17. Builder continues only after the state file names the next authorized action.

Safe to run in parallel after the Builder has opened a PR:

- QA reviewing the PR.
- Security reviewing the PR.
- Eval Builder proposing eval cases.
- Eval running behavior checks.
- Watchdog reviewing completed reports and event logs.
- Blocker Remediation preparing a fix plan after gates fail.
- Documentation updating state from completed reports.

Not safe to run in parallel:

- Multiple Builders implementing different phases in the same production files.
- QA, Security, Eval Builder, Eval, Watchdog, Blocker Remediation, Architect, or Documentation changing production implementation without explicit authorization.
- Any loop changing model-call payloads, schema, auth behavior, or user-facing classifications outside the authorized phase.

## Optional Roadmap Phase Structure

If the user asks for phase planning or provides a roadmap, include a compact phase structure:

```markdown
Phase 0: Baseline and shared state
Phase 1: Stabilization
Phase 2: Targeted behavior improvements
Phase 3: Scale, performance, and edge cases
Phase 4: Release hardening
Phase 5: Production rollout and monitoring
```

Adapt the phase names to the user's roadmap. Do not invent implementation details that conflict with preserved components or forbidden changes.

## Adaptation Instructions

To adapt the orchestration package to another project:

1. Replace project, repo, roadmap, phase, and objective values.
2. Replace preserved components and forbidden changes.
3. Set allowed and forbidden files for the current phase.
4. Define the write lock owner, scope, authorized phase, unauthorized phases, and phase exit requirements.
5. Set the active branch, PR, and test command.
6. Define controlled taxonomy terms that must not drift across loops.
7. Identify high-risk areas that require Security review.
8. Identify eval fixtures or behavior examples that catch regressions.
9. Decide whether Eval Builder should create or update fixtures for the phase.
10. Define Watchdog checks for product quality, eval quality, and process integrity.
11. Decide which actions require Human Product Owner approval.
12. Create or update the shared state file.
13. Create the runtime harness when long-running loop scaffolding is requested.
14. Run the loop sequence without allowing parallel production-code edits.

## Example Invocation

```markdown
Use the multi-agent-orchestration skill.
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
Runtime harness required: yes
Eval Builder required: yes
Watchdog required: yes
Controlled taxonomy:
- verdict
- reason_code
- direction
- coverage_gate
- confidence
- human_review_required
Eval examples:
- wrong-domain MFA should not contradict
- remote VPN MFA should not support all privileged MFA
- annual vs quarterly should contradict
- quarterly vs annual should support
- policy silent should not be called contradiction
- vague policy should become needs_review
- fragment extraction should not hard contradict
```

The response should generate the full orchestration setup using the required output format and fill missing fields with placeholders.
