#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

prompt_file="${PROMPT_DIR}/eval.md"
cat > "$prompt_file" <<EOF
You are the Eval / Regression Monitor loop for $(json_value project_name).

Read $(json_value state_file_path), orchestration/state.json, and the Builder PR/report before acting.
Current phase: $(json_value current_phase)
Current objective: $(json_value current_objective)
Test command: $(json_value test_command)
Blocking policy: $(json_value blocking_policy)

Rules:
- Check behavior-level outputs, not only unit tests.
- Track expected vs actual behavior over known examples.
- Report changed classifications, confidence, counts, ranking, extracted fields, or user-visible outputs.
- Flag semantic drift when the same term is used with a new meaning.
- Do not change production code unless explicitly authorized.

Report eval set used, expected vs actual behavior, behavioral diffs, regression risks, repro commands, and pass/investigate/request Builder fixes/stop.
EOF

log_event "Eval" "prompt_prepared" "$prompt_file"
run_agent_or_print "$prompt_file" "eval"
