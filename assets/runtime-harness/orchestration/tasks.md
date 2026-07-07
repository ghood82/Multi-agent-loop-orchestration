# Orchestration Tasks

Project: {{PROJECT_NAME}}
Roadmap: {{ROADMAP_NAME}}
Current phase: {{CURRENT_PHASE}}
Current objective: {{CURRENT_OBJECTIVE}}

## Active Gates

- [ ] Shared state reviewed.
- [ ] Daemon queue/cursor reviewed.
- [ ] Write lock owner confirmed.
- [ ] Authorized phase confirmed.
- [ ] Builder PR opened.
- [ ] QA verification complete.
- [ ] Security review complete when applicable.
- [ ] Eval Builder coverage complete when needed.
- [ ] Eval/regression check complete.
- [ ] Watchdog product-quality review complete.
- [ ] Watchdog eval-quality review complete.
- [ ] Watchdog process-integrity review complete.
- [ ] Blocker remediation plan complete when blockers or non-PASS Watchdog verdict exist.
- [ ] Architect decision recorded.
- [ ] Human Product Owner approval recorded when required.
- [ ] Documentation state updated.

## Next Authorized Action

Architect assigns first Builder task.

## Blocking Policy

Mode: stop-and-ask
Recovery limit: 1 low-risk mechanical recovery attempt
Default action: Stop, summarize the blocker, recommend next action, and wait for human direction.
Immediate stop: security/privacy risk, schema migration, auth changes, external model behavior, preserved-component removal, API compatibility risk, product judgment, repeated test failures, process drift, unclear requirements.

## Stop Report

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
