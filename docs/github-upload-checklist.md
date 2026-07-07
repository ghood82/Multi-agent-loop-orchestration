# GitHub Upload Checklist

Use this checklist before publishing the repository.

## Required Before Upload

- Run `python3 scripts/smoke_test_runtime_harness.py`.
- Confirm there are no secrets, credentials, local paths, or private project details.
- Confirm generated temporary files are not included.
- Confirm `.github/workflows/smoke-test.yml` is present.
- Choose whether the repository should be public or private.

## Required Before Public Release

- Replace `LICENSE.md` with the selected license.
- Replace the placeholder disclosure channel in `SECURITY.md`.
- Confirm the README does not overstate autonomy or security guarantees.
- Create an initial GitHub release or tag only after the smoke workflow passes.

## Suggested Git Commands

```bash
git init
git add .
git diff --cached --check
git commit -m "Initial multi-agent orchestration skill package"
git branch -M main
git remote add origin git@github.com:OWNER/REPO.git
git push -u origin main
```
