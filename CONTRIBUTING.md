# Contributing

Thanks for taking the time to improve this package.

## Development Loop

1. Create a branch for the change.
2. Keep changes scoped to the skill, scripts, docs, or harness assets.
3. Run the smoke test before opening a pull request:

```bash
python3 scripts/smoke_test_runtime_harness.py
```

4. Update docs when behavior, command flags, gate semantics, or runtime boundaries change.

## Design Constraints

- Preserve the single-production-writer rule.
- Keep provider-specific behavior isolated to the agent adapter layer.
- Do not turn process guards into claims of filesystem or security enforcement.
- Do not bypass human approval for high-impact product, security, privacy, auth, schema, or release decisions.
- Prefer explicit evidence artifacts over implied status.

## Pull Request Checklist

- Smoke test passes.
- New or changed commands are documented.
- Runtime boundary language remains accurate.
- No secrets, local paths, or project-specific private details are committed.
- Generated reports and temporary artifacts are not committed unless they are intentional fixtures.
