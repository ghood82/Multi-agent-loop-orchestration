#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

lock_status="$(lock_value status)"
lock_owner="$(lock_value owner)"

if [[ "$lock_status" == "active" && "$lock_owner" != "Builder" ]]; then
  echo "Stop: production-code write lock is active for ${lock_owner}." >&2
  log_event "Builder" "stopped" "Write lock held by ${lock_owner}"
  exit 2
fi

prompt_file="${PROMPT_DIR}/builder.md"
cat > "$prompt_file" <<EOF
You are the Builder loop for $(json_value project_name).

Read $(json_value state_file_path) and orchestration/state.json before acting.
Current phase: $(json_value current_phase)
Current objective: $(json_value current_objective)
Authorized phase: $(json_value phase_gate.authorized_phase)
Test command: $(json_value test_command)
Blocking policy: $(json_value blocking_policy)

Rules:
- Confirm the production-code write lock is assigned to Builder before editing production code.
- Implement only the authorized phase.
- Do not remove preserved components or make forbidden changes.
- Add or update tests for changed behavior.
- Run relevant tests and repeat the fix/test loop up to 5 times.
- Stop on unclear requirements, repeated test failure, schema risk, security risk, CI block, or product judgment.

Report summary, files changed, tests run, lock status, PR status, risks, and recommended next handoff.
EOF

log_event "Builder" "prompt_prepared" "$prompt_file"
run_agent_or_print "$prompt_file" "builder"
