"""Unit tests for run-cycle orchestration sequencing."""

from __future__ import annotations

from pathlib import Path

from _helpers import load_source, ns

rc = load_source("run_cycle", "run-cycle.py")


def cycle_args(**overrides):
    base = {
        "roles": "docs",
        "agent_command": "",
        "create_branch": "",
        "commit_message": "",
        "push": True,
        "create_pr": True,
        "pr_title": "",
        "base": "",
        "allow_git_write": True,
        "allow_dirty_branch_create": False,
        "skip_watchdog_pr_check": False,
        "strict_gates": False,
        "remediate_on_gate_failure": False,
        "require_ci_pass": True,
        "require_latest_eval_pass": False,
        "policy": "operating-policy.json",
        "no_policy": True,
        "watch_ci": True,
        "ci_pr": "",
        "ci_required": False,
        "ci_timeout_seconds": 0.0,
        "ci_from_file": "",
        "require_human_approval": False,
        "no_normalize_reports": False,
        "open_blockers_from_reports": False,
        "dispatch_subagents": False,
        "subagent_command": "",
        "subagent_open_blockers": False,
        "subagent_fail_on_negative": False,
        "disable_file_guard": False,
        "no_file_guard_blocker": False,
        "release_gate": False,
        "release_mode": "status",
        "release_pr": "",
        "release_pr_from_file": "",
        "release_open_blocker": False,
        "release_strict_file_guard": False,
        "allow_draft_pr": False,
        "allow_review_pending": False,
        "sync_state_doc": False,
    }
    base.update(overrides)
    return ns(**base)


def test_push_create_pr_watch_ci_refreshes_after_pr_before_ci_required_gate(
    monkeypatch, tmp_path: Path
):
    args = cycle_args()
    events: list[str] = []

    monkeypatch.setattr(rc, "parse_args", lambda: args)
    monkeypatch.setattr(rc, "apply_policy_defaults", lambda root, args: events.append("policy"))
    monkeypatch.setattr(rc, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(rc, "create_branch", lambda repo, args: events.append("create-branch"))
    monkeypatch.setattr(rc, "run_roles", lambda *a, **kw: events.append("roles") or [])
    monkeypatch.setattr(rc, "normalize_reports", lambda *a, **kw: events.append("normalize") or [])
    monkeypatch.setattr(
        rc, "dispatch_subagents_if_requested", lambda *a: events.append("subagents")
    )
    monkeypatch.setattr(rc, "sync_state_doc_if_requested", lambda *a: events.append("sync-state"))
    monkeypatch.setattr(rc, "commit_changes", lambda repo, args: events.append("commit"))
    monkeypatch.setattr(rc, "push_branch", lambda repo, args: events.append("push"))
    monkeypatch.setattr(rc, "create_pr", lambda repo, root, args: events.append("create-pr"))
    monkeypatch.setattr(
        rc, "refresh_ci_if_requested", lambda root, bin_dir, args: events.append("watch-ci")
    )
    monkeypatch.setattr(
        rc,
        "run_release_gate_if_requested",
        lambda root, bin_dir, args, action, require_ci=None: events.append(
            f"release:{action}:{require_ci}"
        ),
    )
    monkeypatch.setattr(
        rc,
        "validate_pr_creation_gates",
        lambda root, bin_dir, args, require_ci=None: events.append(f"validate-pr:{require_ci}"),
    )
    monkeypatch.setattr(
        rc,
        "enforce_strict_gates",
        lambda root, bin_dir, args, action, require_ci=None: events.append(
            f"strict:{action}:{require_ci}"
        ),
    )

    assert rc.main() == 0

    assert events.index("push") < events.index("create-pr") < events.index("watch-ci")
    assert events.index("watch-ci") < events.index("validate-pr:True")
    assert "validate-pr:False" in events
    assert events.index("validate-pr:False") < events.index("push")


def test_non_deferred_path_preserves_default_ci_gate_behavior(monkeypatch, tmp_path: Path):
    args = cycle_args(watch_ci=False, require_ci_pass=False)
    events: list[str] = []

    monkeypatch.setattr(rc, "parse_args", lambda: args)
    monkeypatch.setattr(rc, "apply_policy_defaults", lambda root, args: events.append("policy"))
    monkeypatch.setattr(rc, "git_root", lambda root: tmp_path)
    monkeypatch.setattr(rc, "create_branch", lambda repo, args: events.append("create-branch"))
    monkeypatch.setattr(rc, "run_roles", lambda *a, **kw: events.append("roles") or [])
    monkeypatch.setattr(rc, "normalize_reports", lambda *a, **kw: events.append("normalize") or [])
    monkeypatch.setattr(
        rc, "dispatch_subagents_if_requested", lambda *a: events.append("subagents")
    )
    monkeypatch.setattr(rc, "sync_state_doc_if_requested", lambda *a: events.append("sync-state"))
    monkeypatch.setattr(rc, "commit_changes", lambda repo, args: events.append("commit"))
    monkeypatch.setattr(rc, "push_branch", lambda repo, args: events.append("push"))
    monkeypatch.setattr(rc, "create_pr", lambda repo, root, args: events.append("create-pr"))
    monkeypatch.setattr(
        rc,
        "refresh_ci_if_requested",
        lambda root, bin_dir, args: events.append("watch-ci") if args.watch_ci else None,
    )
    monkeypatch.setattr(
        rc,
        "run_release_gate_if_requested",
        lambda root, bin_dir, args, action, require_ci=None: events.append(
            f"release:{action}:{require_ci}"
        ),
    )
    monkeypatch.setattr(
        rc,
        "validate_pr_creation_gates",
        lambda root, bin_dir, args, require_ci=None: events.append(f"validate-pr:{require_ci}"),
    )
    monkeypatch.setattr(
        rc,
        "enforce_strict_gates",
        lambda root, bin_dir, args, action, require_ci=None: events.append(
            f"strict:{action}:{require_ci}"
        ),
    )

    assert rc.main() == 0

    assert "watch-ci" not in events
    assert "validate-pr:None" in events
    assert "strict:PR creation:None" in events
    assert events.index("validate-pr:None") < events.index("push") < events.index("create-pr")
    assert "validate-pr:True" not in events
