# Multi-Agent Orchestration Skill

`multi-agent-orchestration` is a Codex skill and local runtime harness for coordinating AI-assisted software work across Builder, QA, Security, Eval, Watchdog, Architect, Documentation, and Remediation roles.

The core invariant is simple: only one loop should write production code at a time. Reviewer loops can run in parallel, but production-code edits stay sequential and are governed through shared state, handoff packets, write-lock conventions, gates, and human approval requirements.

## What This Repository Contains

- `SKILL.md` - the Codex skill instructions.
- `README.md` - this GitHub-facing overview.
- `docs/operator-guide.md` - the detailed operator guide from the skill package.
- `scripts/create_runtime_harness.py` - installs the runtime harness into a target repo.
- `scripts/adopt_project.py` - one-command first-time adoption flow.
- `scripts/smoke_test_runtime_harness.py` - validates the packaged harness.
- `assets/runtime-harness/` - the project-local orchestration control plane template.
- `agents/openai.yaml` - skill agent metadata.

## What It Installs Into A Target Repo

The runtime harness creates an `orchestration/` folder with:

- shared state in `orchestration/state.json`
- synced human-readable roadmap state
- role prompt runners
- health, status, doctor, acceptance audit, and requirements-matrix checks
- CI, release, phase, decision, and human approval gates
- write-lock and file-guard conventions
- handoff packets and stop reports
- eval fixtures/results and project-quality rubrics
- provider adapter support for automatic detection, Codex CLI, Claude Code, prompt-only mode, or a custom command

This is a local control plane. It does not replace CI, branch protection, code review, deployment review, security review, or human product ownership.

## Requirements

- Python 3.10 or newer
- Git for the smoke test and target repo validation
- Optional: Codex CLI or Claude Code if you want role runners to execute through a local agent command

No third-party Python packages are required for the packaged smoke test.

## Validate The Package

Run this from the repository root:

```bash
python3 scripts/smoke_test_runtime_harness.py
```

Expected result:

```text
Smoke test passed.
```

The smoke test creates temporary git repos, installs the harness, runs health and acceptance checks, records state, creates and resolves a blocker, and verifies the one-command adoption path.

## Install The Harness Into A Repo

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

For first-time adoption with setup, ops checks, and a Builder handoff packet:

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

## Use As A Codex Skill

Clone or copy this folder to a Codex skill path using the folder name `multi-agent-orchestration`, then invoke it with a prompt like:

```text
Use the multi-agent-orchestration skill to set up orchestration for this repo.
Ask me only the setup questions you need.
```

The skill should ask only for setup details that materially affect safety:

1. project/repo
2. roadmap or current objective
3. current phase
4. package-only vs runtime harness install
5. test command and CI/PR check source
6. preserved components and forbidden changes
7. blocker-handling policy
8. agent runtime preference
9. decision policy

When values are unknown, the skill should use `TBD` placeholders unless missing details would make setup unsafe.

## Normal Operating Flow

The intended sequence is:

```text
Builder -> QA -> Security -> Eval Builder -> Eval -> Watchdog -> Architect -> Docs
```

High-impact behavior, security/privacy risk, schema migration, auth changes, external model behavior, preserved-component removal, API compatibility risk, product judgment, repeated test failures, process drift, or unclear requirements should stop for human direction.

## Runtime Boundaries

This package provides orchestration state, prompts, local runner scripts, evidence capture, and gates. It does not magically grant safe autonomy.

Before treating it as an autonomous operating system in a real repo, verify:

- provider execution is configured and working
- CI evidence is connected
- project-specific eval fixtures exist
- release and human approval gates match the repo's risk profile
- branch protection and code review remain active
- file guards are treated as process checks, not filesystem security controls

See [docs/runtime-boundaries.md](docs/runtime-boundaries.md) for the detailed boundary statement.

## Repository Hygiene

This repo is prepared for GitHub with:

- a smoke-test GitHub Actions workflow
- `.gitignore` and `.gitattributes`
- contribution and security docs
- an explicit license placeholder
- an upload checklist

Before making the repo public, choose a real license and replace `LICENSE.md`.

## License

No open-source license has been selected yet. See [LICENSE.md](LICENSE.md).
