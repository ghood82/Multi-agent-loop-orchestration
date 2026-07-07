# Example Run

This is a real, end-to-end walkthrough of the harness on a throwaway repo — a
one-file "Demo Service" whose only product code is a `greet()` function. Every
command and its output below was captured from an actual run; nothing here is
mocked. Paths use a temporary directory (`/tmp/.../demo-service`).

The point is to show the headline guarantee working: **once the harness is
installed, production code cannot be committed unless the Builder holds an
active, in-scope write lock.**

To reproduce, run the same commands against any git repo.

## 0. A tiny product, committed before the harness

```console
$ git init -q && git config user.email demo@example.com && git config user.name Demo

$ cat > src/app.py <<'PY'
def greet(name):
    return f"Hello, {name}!"
PY

$ git add src/app.py && git commit -q -m 'initial product' && git log --oneline
4603b5c initial product
```

## 1. Install the harness

The write-lock pre-commit hook installs automatically when the target is a git
repo (opt out with `--no-install-hooks`).

```console
$ python3 scripts/create_runtime_harness.py --target . \
    --project-name 'Demo Service' --repo-name demo-service --roadmap-name 'Demo Roadmap' \
    --current-phase 'Phase 1: harden greet()' \
    --current-objective 'Add input validation without changing the public API' \
    --test-command 'python -m pytest'
...
- orchestration/tasks.md
- orchestration/worktrees/.gitkeep
Installed write-lock pre-commit hook at .../demo-service/.git/hooks/pre-commit.
```

## 2. Record the scope

Tell the harness what the Builder may touch this phase, and what is off-limits.

```console
$ python3 orchestration/bin/configure-project.py \
    --allowed-file 'src/**' \
    --preserved-component 'src/app.py greet() signature' \
    --forbidden-change 'do not change greet() return type' \
    --sync-state-doc
configured
```

## 3. A production edit with no lock is blocked

The Builder adds input validation to `greet()` and tries to commit — but has not
acquired the write lock yet. The pre-commit hook refuses it:

```console
$ git add src/app.py && git commit -m 'add validation'
Write-lock enforcement found unauthorized changes:
  - no active write lock: production-code changes require an active lock held by Builder (activate it via the harness before editing production code)

Acquire/adjust the production-code write lock through the orchestration harness, move the change into scope, or bypass in an emergency with ORCH_ALLOW_LOCK_OVERRIDE=1 (or `git commit --no-verify`).

# exit code: 1 — the commit did not happen
```

## 4. The Builder acquires the write lock

The lock lives in shared state, scoped to this phase:

```console
$ python3 orchestration/bin/update-state.py set write_lock.status active
$ python3 orchestration/bin/update-state.py set write_lock.scope 'Phase 1: harden greet()'
write lock is now active
```

## 5. The same in-scope commit now passes

`src/app.py` is inside `allowed_files` (`src/**`), so the hook lets it through:

```console
$ git commit -m 'add validation'
Write-lock check passed.
[master 7a1fa7e] add validation
 1 file changed, 2 insertions(+)
```

## 6. An out-of-scope change is still blocked

Even with the lock active, a change outside `src/**` is refused — the lock
authorizes a scope, not a blank cheque:

```console
$ echo "def charge(): ..." > billing/charge.py
$ git add billing/charge.py && git commit -m 'unrelated billing change'
Write-lock enforcement found unauthorized changes:
  - out of scope: billing/charge.py is outside the active write lock's allowed_files
...

# exit code: 1 — the commit did not happen
```

## 7. A high-risk decision stops for a human

The gates escalate what they should. Classifying a return-type change as
high-risk returns `HUMAN_REQUIRED` and exits non-zero:

```console
$ python3 orchestration/bin/decision-gate.py --risk high \
    --decision 'Change greet() return type to a dict' \
    --evidence 'reports/json/x.json'
Decision: HUMAN_REQUIRED
Risk: high
Report: .../orchestration/reports/json/20260707T210916791338Z-decision-gate.json
Recommended next action: Create or update an approval request and wait for Human Product Owner decision.
```

## 8. The state and event trail

The shared state records the active lock:

```console
$ python3 -c "import json; print(json.dumps(json.load(open('orchestration/state.json'))['write_lock'], indent=2))"
{
  "allowed_files": [
    "src/**"
  ],
  "forbidden_files": [],
  "owner": "Builder",
  "scope": "Phase 1: harden greet()",
  "status": "active"
}
```

And every step is appended to the append-only event log:

```console
$ tail -n 5 orchestration/events.log
{"event": "configured", "note": "Demo Service", "role": "configure-project", "ts": "..."}
{"event": "synced", "note": ".../docs/project-roadmap-state.md", "role": "state-doc-sync", "ts": "..."}
{"event": "set", "note": "write_lock.status updated", "role": "State", "ts": "..."}
{"event": "set", "note": "write_lock.scope updated", "role": "State", "ts": "..."}
{"event": "HUMAN_REQUIRED", "note": "reports/json/...-decision-gate.json", "role": "decision-gate", "ts": "..."}
```

## What this shows

- Production edits are gated on an **active, in-scope** write lock — enforced at
  the commit boundary, not merely recorded after the fact.
- The lock authorizes a **scope** (`allowed_files`), so a held lock still can't
  wander into unrelated code.
- Bypasses are possible (`--no-verify`, `ORCH_ALLOW_LOCK_OVERRIDE=1`) but loud,
  so they surface in review — see [runtime-boundaries.md](runtime-boundaries.md).
- Risk gates escalate high-impact decisions to a human instead of proceeding.
