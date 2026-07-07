#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPDATE_STATE="${ROOT_DIR}/bin/update-state.py"

provider="${1:-github}"
conclusion="${2:-}"
details="${3:-}"
url="${4:-}"

if [[ -z "$conclusion" && "$provider" == "github" ]] && command -v gh >/dev/null 2>&1; then
  json="$(gh run list --limit 1 --json conclusion,status,url,name 2>/dev/null || true)"
  if [[ -n "$json" && "$json" != "[]" ]]; then
    conclusion="$(python3 - "$json" <<'PY'
import json, sys
data=json.loads(sys.argv[1])
print((data[0].get("conclusion") or data[0].get("status") or "unknown") if data else "unknown")
PY
)"
    details="$(python3 - "$json" <<'PY'
import json, sys
data=json.loads(sys.argv[1])
print(data[0].get("name", "") if data else "")
PY
)"
    url="$(python3 - "$json" <<'PY'
import json, sys
data=json.loads(sys.argv[1])
print(data[0].get("url", "") if data else "")
PY
)"
  fi
fi

if [[ -z "$conclusion" ]]; then
  echo "Usage: capture-ci.sh [provider] <conclusion> [details] [url]" >&2
  echo "Or run inside a GitHub repo with gh installed to infer the latest run." >&2
  exit 2
fi

python3 "$UPDATE_STATE" ci \
  --provider "$provider" \
  --conclusion "$conclusion" \
  --details "$details" \
  --url "$url"
