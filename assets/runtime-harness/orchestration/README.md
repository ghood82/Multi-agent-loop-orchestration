# Orchestration Runtime Guide

This folder is the project-local control plane for the multi-agent orchestration workflow.

Core invariant: only one loop writes production code at a time. Builder owns production-code edits by default. QA, Security, Eval, Architect, Watchdog, Documentation, and subagents inspect, verify, coordinate, or record unless a human explicitly authorizes otherwise.

## First Checks

Run these after installing the harness:

```bash
python3 orchestration/bin/setup-intake.py
```

For non-interactive setup:

```bash
python3 orchestration/bin/configure-project.py --project-name "PROJECT" --repo-name "REPO" --roadmap-name "ROADMAP" --current-phase "PHASE" --current-objective "OBJECTIVE" --sync-state-doc
python3 orchestration/bin/health-check.py --write-report
python3 orchestration/bin/acceptance-audit.py --write-report
python3 orchestration/bin/sync-state-doc.py --write-report
python3 orchestration/bin/status.py --write-report
python3 orchestration/bin/ops-check.py --strict
python3 orchestration/bin/doctor.py --write-report
python3 orchestration/bin/requirements-matrix.py --write-report --strict
python3 orchestration/bin/handoff-packet.py --write --write-report
```

`setup-intake.py` can also apply setup and verify the operating system in one step. This is the runtime half of the one-command adoption path provided by the skill package:

```bash
python3 orchestration/bin/setup-intake.py --apply --run-ops-check
```

Expected clean setup:

- health-check: `PASS`
- acceptance audit: `PASS`
- shared roadmap state markdown is synced
- status.py operating decision: `CONTINUE`
- ops-check: `PASS`
- doctor records the next exact command
- requirements-matrix: `PASS`
- open blockers: `0`

## Normal Loop

Run one authorized step:

```bash
bash orchestration/bin/orchestration-daemon.sh --resume-plan --sync-state-doc --max-steps 1
python3 orchestration/bin/status.py --write-report
python3 orchestration/bin/handoff-packet.py --write --write-report
```

For longer autonomous runs, bound the loop so it stops for a human instead of spinning (and burning agent spend) on an unresolvable blocker:

```bash
bash orchestration/bin/orchestration-daemon.sh --continuous \
  --max-remediation-attempts 3 \   # pause after 3 consecutive remediation runs
  --max-wall-seconds 1800 \        # stop after 30 minutes of wall-clock time
  --max-steps 50                   # hard cap on total role executions
```

When the remediation budget is hit the daemon records `daemon.status = paused_budget` and stops. All budgets default to unlimited (`0`), so existing behavior is unchanged unless you opt in.

Require real work before advancing so a no-op or prompt-only run cannot walk the queue with nothing to show:

```bash
bash orchestration/bin/orchestration-daemon.sh --continuous --require-role-completion
```

With `--require-role-completion`, the daemon advances only when the role produced a completion signal — a fresh verdict bound to the current HEAD (recorded via the result contract), or a new commit for Builder/Remediation. Otherwise it records `daemon.status = paused_incomplete` and stops. Off by default.

## Agent Adapter

Role runners use `orchestration/bin/agent-adapter.py`. The default provider is `auto`, which resolves to Codex CLI when `codex` is installed, then Claude Code when `claude` is installed, then `prompt-only` when neither runtime is available.

To force a provider command:

```bash
AGENT_PROVIDER=codex-cli bash orchestration/bin/run-builder.sh
AGENT_PROVIDER=claude-code bash orchestration/bin/run-builder.sh
AGENT_PROVIDER=prompt-only bash orchestration/bin/run-builder.sh
```

To test provider resolution without launching an agent:

```bash
python3 orchestration/bin/agent-adapter.py --role smoke --prompt-file orchestration/README.md --provider auto --resolve-only --json
```

Configure a named provider preset:

```bash
python3 orchestration/bin/configure-agent-provider.py --list
python3 orchestration/bin/configure-agent-provider.py --provider auto
python3 orchestration/bin/configure-agent-provider.py --provider codex-cli --command "codex exec"
python3 orchestration/bin/configure-agent-provider.py --provider claude-code --command "claude -p"
python3 orchestration/bin/configure-agent-provider.py --provider custom-command --command "your-agent-command" --test
```

## Doctor

Use the doctor for one operator-facing answer:

```bash
python3 orchestration/bin/doctor.py --write-report
```

## Requirements Matrix

Use the requirements matrix for a line-by-line completion audit:

```bash
python3 orchestration/bin/requirements-matrix.py --write-report --strict
```

Default handoff sequence:

```text
Builder -> QA -> Security -> Eval Builder -> Eval -> Watchdog -> Architect -> Docs
```

## Gates

Repo-level defaults live in `orchestration/operating-policy.json`. Keep the default profile during bring-up, then use `configure-project.py` to turn on stricter gates when the repo has eval, CI, and approval evidence:

```bash
python3 orchestration/bin/configure-project.py --policy-profile strict-pr --policy-require-latest-eval-pass true --policy-require-ci-pass true --policy-require-human-approval true --policy-strict-gates true
```

Audit the active policy and missing evidence:

```bash
python3 orchestration/bin/policy-audit.py --write-report --strict
```

Generate the human operating dashboard:

```bash
python3 orchestration/bin/operating-dashboard.py --write-report
```

Run the consolidated readiness check:

```bash
python3 orchestration/bin/ops-check.py --strict
```

This records one verdict across health, policy audit, phase gate, release gate, operator status, state-doc sync, and dashboard generation.

Gate phase advancement:

```bash
python3 orchestration/bin/phase-gate.py --write-report --strict
python3 orchestration/bin/phase-gate.py --advance-to "Phase 2" --write-report --strict
```

Use release gate before PR, merge, or release actions:

```bash
python3 orchestration/bin/release-gate.py --mode merge --require-ci-pass --require-latest-eval-pass --require-human-approval
```

Human Product Owner approval is required before major decisions such as merging major PRs, schema migrations, changing auth/security behavior, changing external model behavior, changing user-facing verdicts/classifications, removing preserved components, or shipping to production.

Use the decision gate to classify decisions before action:

```bash
python3 orchestration/bin/decision-gate.py --risk low --decision "Refresh generated reports" --evidence "reports/json/example.json"
python3 orchestration/bin/decision-gate.py --risk medium --decision "Adjust current-phase matching logic" --research-summary "Compared options and no external behavior contract changes." --confidence 0.85 --evidence "reports/json/qa.json"
python3 orchestration/bin/decision-gate.py --risk high --decision "Change user-facing classification semantics" --evidence "reports/json/watchdog.json" --open-blocker
```

Low-risk decisions may proceed autonomously with evidence. Medium-risk decisions require research and confidence before proceeding; escalate if product impact is unclear. High-risk decisions require Human Product Owner approval.

Create an approval request before asking for the final decision:

```bash
python3 orchestration/bin/approval-request.py --scope "Merge phase PR" --reason "Human approval required before merge" --recommendation "Approve only if release gate passes" --open-blocker
```

## Blockers

Record blockers with evidence:

```bash
python3 orchestration/bin/update-state.py add-blocker "Describe the blocker" --severity high --owner watchdog
```

Create a formal stop report when a loop cannot safely continue:

```bash
python3 orchestration/bin/stop-report.py --stop-reason "Product judgment required" --what-failed "Verdict behavior would change" --recommended-next-action "Human Product Owner decision required" --open-blocker
```

Plan a recovery path:

```bash
python3 orchestration/bin/resume-plan.py --apply --prefer-remediation --write-report
bash orchestration/bin/run-remediation.sh
```

Resolve blockers only with evidence:

```bash
python3 orchestration/bin/update-state.py resolve-blocker blocker-id --evidence "What proved this is fixed"
```

## Result Contract And Fresh Evidence

The orchestrator records a role's verdict from a machine-readable block rather than guessing from prose. Each role appends this to its prompt, and returns it filled in:

```orchestration-result
{"verdict": "PASS", "summary": "one line", "blockers": [], "tests": [], "risks": []}
```

When present, the block is authoritative — no scraping of the surrounding prose. `normalize-report.py --require-structured` (or `run-cycle.py --require-structured`, or `gates.require_structured` in the operating policy) fails the role and opens a blocker when the block is missing or malformed, so a role that produces no real verdict cannot silently pass.

Every verdict is stamped with the commit SHA it reviewed, in `state.json` under `role_verdicts`. Turn on freshness enforcement so a PASS recorded for an older commit cannot gate a newer, unreviewed change:

```bash
python3 orchestration/bin/run-cycle.py --strict-gates --require-fresh-evidence ...
```

or set `gates.require_fresh_evidence: true` (and `gates.require_structured: true`) in `operating-policy.json`. A required verdict then counts only when its stamped commit matches the current HEAD.

## Watchdog And Subagents

Watchdog checks product quality, eval quality, process integrity, and drift. It can recommend `PASS`, `REQUEST_FIXES`, or `STOP`, but it does not replace Human Product Owner judgment.

Before Watchdog runs, prepare the evidence packet:

```bash
python3 orchestration/bin/prepare-watchdog-evidence.py --write-report
```

`run-watchdog.sh` runs this automatically. The packet records connected tests, eval fixtures/results, latest reports, PR diff evidence, and the project quality rubric. If any required evidence is missing, Watchdog should not return `PASS`.

When Eval Builder is authorized to turn a behavior risk into a reusable regression artifact, create a fixture:

```bash
python3 orchestration/bin/eval-fixture.py create \
  --name "Wrong-domain policy match stays non-contradictory" \
  --input "Procedure mentions annual review; policy evidence comes from unrelated credentialing section." \
  --expected "Do not classify as contradiction without same-domain policy evidence" \
  --tolerance "May return needs-review when evidence is insufficient" \
  --risk "false positive user-facing verdict" \
  --write-report
```

Fixtures live under `orchestration/evals/fixtures/` and are recorded in `state.json` so Eval Monitor, Watchdog, Architect, and Documentation can use the same evidence.

When Eval Monitor runs a fixture, record the result:

```bash
python3 orchestration/bin/eval-result.py record \
  --fixture "evals/fixtures/wrong-domain-policy-match.json" \
  --verdict DRIFT \
  --actual '{"classification":"contradiction"}' \
  --diff "Actual classification contradicted expected non-contradiction behavior" \
  --recommended-next-action "Builder fixes the regression, then Eval Monitor reruns" \
  --open-blocker \
  --write-report
```

Eval result artifacts live under `orchestration/evals/results/`. Eval Monitor must record expected vs actual behavior for behavior-level checks. Non-`PASS` results should normally become blockers before Builder, Watchdog, Architect, PR, merge, or release work continues.

Subagents are read-only specialists by default. They may inspect and report findings, but they must not edit production files unless the active loop has explicit authorization and Builder owns the production-code write lock.

## Concurrency-Safe State

`state.json` is the shared source of truth, and several processes can touch it at once — the daemon, a hand-run command, and parallel subagents. Writes go through `orchestration_state.py`, which:

- writes atomically (temp file + `os.replace`), so a reader never sees a half-written, invalid file; and
- holds an advisory `flock` across each read-modify-write, so concurrent processes serialize instead of silently clobbering one another's blockers, verdicts, or reports.

The lock is held from `load_state()` until the matching `save_state()` (or process exit). The runtime lock/temp files (`.state.lock`, `.state.*.tmp`) are git-ignored. On non-POSIX platforms without `flock`, writes stay atomic but are not cross-process locked.

## File Guard

The file guard is a process-drift detector, not an operating-system sandbox. It snapshots files before each role, checks what changed afterward, records violations, and can open blockers when a read-only role or subagent changes files it should not touch. It helps stop unsafe handoffs, but it does not replace branch protection, CI, code review, or filesystem permissions.

## Write-Lock Enforcement

The write lock stops being advisory here. `enforce-write-lock.py` fails an operation *before* an unauthorized production-code change can land, rather than only recording it afterward like the file guard does.

A production-code change is authorized only when the shared write lock in `state.json` is `active` and the change stays inside the lock's `allowed_files`. Changes to `forbidden_files`, `preserved_components`, or declared `forbidden_changes` are never authorized without human sign-off. Docs, markdown, and the `orchestration/` control plane are never treated as production code.

Installed as a pre-commit hook (automatically when the harness lands in a git repo):

```bash
python3 orchestration/bin/install-hooks.py            # install / refresh
python3 orchestration/bin/install-hooks.py --check    # verify, write nothing
```

The hook preserves any pre-existing pre-commit hook as `pre-commit.local` and chains to it. Bypass in an emergency with `ORCH_ALLOW_LOCK_OVERRIDE=1 git commit ...` (reported loudly) or `git commit --no-verify`.

Manage the lock with `write-lock.py`, which keeps `state.json` and the
`locks/production-code.lock` mirror in sync:

```bash
python3 orchestration/bin/configure-project.py --allowed-file "src/**"  # what Builder may touch
python3 orchestration/bin/write-lock.py acquire --owner Builder          # acquire (scoped to allowed_files)
python3 orchestration/bin/write-lock.py status                          # inspect, and check the mirror is in sync
python3 orchestration/bin/write-lock.py release                         # release on handoff
```

`run-builder.sh` acquires the lock for Builder automatically at the start of a
Builder run (and refuses to run if another loop holds it), so in the normal loop
you rarely call `acquire` by hand. Acquiring another loop's active lock requires
`--force`.

Check changes directly:

```bash
python3 orchestration/bin/enforce-write-lock.py --staged                  # staged changes (pre-commit)
python3 orchestration/bin/enforce-write-lock.py --against origin/main --json
```

Add the second layer in CI (a hook can be skipped with `--no-verify`; CI cannot). Copy the template workflow into your repo:

```bash
cp orchestration/ci/write-lock-check.yml .github/workflows/
```

By default the CI check does not require an active lock for every pull request (that would block ordinary human contributions). It always blocks forbidden/preserved paths and enforces the active lock's scope. Add `--require-active-lock` to require an active lock for all production-code changes.
