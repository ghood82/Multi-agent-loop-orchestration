# Project Quality Rubric

Use this rubric before Watchdog gives a final verdict. Replace placeholders with project-specific criteria during first setup or before the first PR gate.

## Objective Fit

- The change directly serves the current objective in `orchestration/state.json`.
- The change stays inside the authorized phase.
- The change does not jump ahead to future roadmap phases.

## Connected Tests

- Primary test command: `[TBD]`
- Additional relevant checks: `[TBD]`
- Required CI/PR checks: `[TBD]`

## Behavior Evals

- Required eval fixtures: `[TBD]`
- Expected user-visible behavior: `[TBD]`
- Drift signals to watch: classifications, counts, confidence, extracted fields, user-facing verdicts, model/API payloads, and output shape.

## PR Diff Review

- Diff stays within allowed files and phase scope.
- Preserved components remain intact.
- Forbidden changes are absent.
- File guard findings are resolved or escalated.

## Security And Privacy

- Sensitive data is not exposed in logs, prompts, reports, fixtures, exports, or external API payloads.
- Auth, authorization, tenant separation, and data-access changes are reviewed when touched.

## Decision Policy

- Low risk: autonomous action is allowed with recorded evidence.
- Medium risk: research first, record rationale and confidence, then escalate if confidence is below threshold or product impact is unclear.
- High risk: human approval is required before action.
