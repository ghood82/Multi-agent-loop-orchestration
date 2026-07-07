# Runtime Boundaries

This package provides a local control plane for coordinating AI-assisted engineering work. It creates state files, role prompts, runner scripts, evidence reports, gates, handoff packets, and stop reports.

It should not be described as a fully autonomous engineering system unless a target repo has also verified provider execution, CI evidence, project-specific evals, release gates, and human approval flow.

## What The Harness Can Do

- Install a project-local `orchestration/` folder.
- Track shared state in `orchestration/state.json`.
- Sync a human-readable roadmap state file.
- Prepare prompts for Builder, QA, Security, Eval Builder, Eval, Watchdog, Architect, Documentation, and Remediation roles.
- Resolve agent provider mode through the adapter.
- Record events and role reports.
- Create handoff packets and stop reports.
- Record blockers, approvals, eval fixtures, and eval results.
- Run health, acceptance, policy, phase, release, doctor, and requirements checks.

## What The Harness Does Not Replace

- CI and branch protection
- code review
- security review
- deployment approval
- secret scanning
- filesystem sandboxing
- provider billing or budget controls
- human product ownership

## File Guard Boundary

The file guard is a process-drift detector. It snapshots and checks changed files around role execution, then records violations or blockers when a role changes files outside its permission model.

It is not an operating-system sandbox. Use git, branch protection, code owners, CI, and repository permissions as the real enforcement layers.

## Write-Lock Enforcement Boundary

`enforce-write-lock.py` is the git-boundary enforcement layer the file guard points to. Installed as a pre-commit hook and (optionally) run in CI, it fails a commit or pull request when a production-code change lands without an active, in-scope write lock, or touches a forbidden file or preserved component.

It still is not a sandbox. A local hook can be skipped with `git commit --no-verify` or `ORCH_ALLOW_LOCK_OVERRIDE=1`, and it trusts the working-tree `state.json` as the source of truth for the current lock. It hardens the single-writer invariant against accidental and automated-loop violations; it does not defend against a determined operator who chooses to bypass it. Keep branch protection, required CI checks, and code review in place as the outer enforcement layers.

## Provider Boundary

The agent adapter can resolve to Codex CLI, Claude Code, prompt-only mode, or a configured custom command. Prompt-only mode prepares artifacts but does not execute an agent.

Before relying on automated loops, run provider resolution and at least one bounded role execution in the target repo.

## Human Approval Boundary

High-impact decisions require human approval by default. This includes product behavior changes, auth changes, schema changes, security/privacy issues, release decisions, preserved-component removal, API compatibility risk, and unclear requirements.
