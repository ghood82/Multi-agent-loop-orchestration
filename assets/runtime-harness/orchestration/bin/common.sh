#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_FILE="${ROOT_DIR}/state.json"
EVENT_LOG="${ROOT_DIR}/events.log"
LOCK_FILE="${ROOT_DIR}/locks/production-code.lock"
PROMPT_DIR="${ROOT_DIR}/prompts"

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "Missing required file: $path" >&2
    exit 1
  fi
}

json_value() {
  local expr="$1"
  python3 - "$STATE_FILE" "$expr" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
value = data
for part in sys.argv[2].split("."):
    if not part:
        continue
    value = value.get(part, "")
if isinstance(value, (list, dict)):
    print(json.dumps(value))
else:
    print(value)
PY
}

lock_value() {
  local expr="$1"
  python3 - "$LOCK_FILE" "$expr" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
value = data
for part in sys.argv[2].split("."):
    if not part:
        continue
    value = value.get(part, "")
if isinstance(value, (list, dict)):
    print(json.dumps(value))
else:
    print(value)
PY
}

log_event() {
  local role="$1"
  local event="$2"
  local note="${3:-}"
  python3 - "$EVENT_LOG" "$role" "$event" "$note" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
entry = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "role": sys.argv[2],
    "event": sys.argv[3],
    "note": sys.argv[4],
}
with path.open("a") as handle:
    handle.write(json.dumps(entry, sort_keys=True) + "\n")
PY
}

# The machine-readable result contract every role appends to its prompt so the
# orchestrator records a verdict from a structured block instead of guessing
# from prose. normalize-report.py --require-structured enforces it.
read -r -d '' RESULT_CONTRACT <<'CONTRACT' || true
---
At the very end of your report, output a machine-readable result block with this
exact fenced tag so the orchestrator can record your verdict without guessing:

```orchestration-result
{"verdict": "PASS", "summary": "one line", "blockers": [], "tests": [], "risks": []}
```

Use verdict PASS (or APPROVED) only when the work meets the bar; otherwise use
REQUEST_FIXES, FAIL, BLOCKED, or STOP and list each blocker explicitly.
CONTRACT

emit_result_contract() {
  local prompt_file="$1"
  printf '\n%s\n' "$RESULT_CONTRACT" >> "$prompt_file"
}

run_agent_or_print() {
  local prompt_file="$1"
  local role="${2:-agent}"
  emit_result_contract "$prompt_file"
  python3 "${ROOT_DIR}/bin/agent-adapter.py" --role "$role" --prompt-file "$prompt_file"
}

require_file "$STATE_FILE"
require_file "$LOCK_FILE"
mkdir -p "$PROMPT_DIR"
