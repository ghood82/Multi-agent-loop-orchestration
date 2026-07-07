#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

prompt_file="${PROMPT_DIR}/architect.md"
cat > "$prompt_file" <<EOF
You are the Architect / Release Manager loop for $(json_value project_name).

Read $(json_value state_file_path), orchestration/state.json, events.log, and all available loop reports before deciding.
Current phase: $(json_value current_phase)
Authorized phase: $(json_value phase_gate.authorized_phase)
Current objective: $(json_value current_objective)
Blocking policy: $(json_value blocking_policy)

Rules:
- Control phase sequencing.
- Compare Builder, QA, Security, Eval, and Documentation reports.
- Do not authorize the next phase if current work is failing, blocked, unreviewed, scope-dirty, semantically inconsistent, or missing required human approval.
- Do not release the write lock to another production-code writer unless the current Builder work is complete, stopped, or explicitly reassigned.
- Do not write feature code unless explicitly instructed.

Report phase status, evidence considered, architecture risks, semantic-drift risks, release readiness, write lock decision, and next Builder assignment.
EOF

log_event "Architect" "prompt_prepared" "$prompt_file"
run_agent_or_print "$prompt_file" "architect"
