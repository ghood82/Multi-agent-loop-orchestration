# Security Policy

## Supported Use

This package is an orchestration harness for AI-assisted engineering workflows. It is not a sandbox, security boundary, deployment system, or replacement for code review.

Keep CI, branch protection, access controls, secret scanning, security review, and human approval in place for real projects.

## Reporting A Security Issue

If this repository is published, replace this section with the maintainer's preferred private disclosure channel before accepting external reports.

Until then, do not post exploitable security details in public issues.

## High-Risk Changes

Changes involving these areas should require human review before merge or release:

- authentication or authorization
- schema migrations
- secrets or credential handling
- logging of sensitive data
- external model behavior
- release gates or approval bypasses
- file guard, lock, or process-control semantics
