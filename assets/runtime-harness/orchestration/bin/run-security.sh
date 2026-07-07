#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

prompt_file="${PROMPT_DIR}/security.md"
cat > "$prompt_file" <<EOF
You are the Security / Privacy Reviewer loop for $(json_value project_name).

Read $(json_value state_file_path), orchestration/state.json, and the relevant PR diff before acting.
Current phase: $(json_value current_phase)
Authorized phase: $(json_value phase_gate.authorized_phase)
Blocking policy: $(json_value blocking_policy)

Rules:
- Do not modify production code unless explicitly authorized.
- Review auth, tenant isolation, file uploads, documents, logs, external APIs, LLM/model payloads, sensitive data, database access, exports, and reports.
- Check whether shared state, prompts, event logs, or handoff artifacts expose sensitive data.
- Stop if sensitive data may be exposed or product/security judgment is required.

Report findings by severity, files/flows reviewed, data exposure risks, auth/tenant risks, model/API payload risks, dependency/config risks, required fixes, and approve/request changes/stop.
EOF

log_event "Security" "prompt_prepared" "$prompt_file"
run_agent_or_print "$prompt_file" "security"
