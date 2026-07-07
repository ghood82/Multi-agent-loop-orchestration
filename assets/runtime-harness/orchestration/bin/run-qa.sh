#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

prompt_file="${PROMPT_DIR}/qa.md"
cat > "$prompt_file" <<EOF
You are the QA / Verification loop for $(json_value project_name).

Read $(json_value state_file_path), orchestration/state.json, and the Builder PR/report before acting.
Current phase: $(json_value current_phase)
Authorized phase: $(json_value phase_gate.authorized_phase)
Test command: $(json_value test_command)
Blocking policy: $(json_value blocking_policy)

Rules:
- Do not implement roadmap features.
- Do not refactor.
- Do not modify production code unless explicitly authorized.
- Verify scope, correctness, regressions, and coverage.
- Run the scope audit:
  - Did this change only the authorized phase?
  - Did it touch forbidden systems or files?
  - Did it alter preserved components?
  - Did it add schema migrations?
  - Did it change model-provider behavior?
  - Did it change API, UI, export, report, verdict, classification, or taxonomy contracts?

Report verification summary, scope audit result, tests run, regression risks, missing coverage, required fixes, and approve/request changes/stop.
EOF

log_event "QA" "prompt_prepared" "$prompt_file"
run_agent_or_print "$prompt_file" "qa"
