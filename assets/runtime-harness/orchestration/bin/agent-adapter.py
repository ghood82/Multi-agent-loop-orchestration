#!/usr/bin/env python3
"""Provider-neutral adapter for invoking an agent with an orchestration prompt."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"
CONFIG_FILE = ROOT / "agent-adapter.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def load_state() -> dict[str, Any]:
    state = load_json(STATE_FILE, {})
    return state if isinstance(state, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log_event(role: str, event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": role, "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def read_prompt(args: argparse.Namespace) -> tuple[str, str]:
    if args.prompt_file:
        path = Path(args.prompt_file)
        if not path.is_absolute():
            path = ROOT.parent / path
        return path.read_text(), str(path)
    return sys.stdin.read(), "stdin"


def command_argv(args: argparse.Namespace, provider: dict[str, Any]) -> list[str]:
    if args.argv:
        return args.argv
    command = args.command or os.environ.get("AGENT_COMMAND") or provider.get("command", "")
    if isinstance(command, list):
        return [str(part) for part in command]
    command_text = os.path.expandvars(str(command or "")).strip()
    if not command_text:
        return []
    return shlex.split(command_text)


def command_available(argv: list[str]) -> bool:
    if not argv:
        return False
    executable = argv[0]
    if os.path.sep in executable:
        return Path(executable).exists()
    return shutil.which(executable) is not None


def provider_by_name(name: str, config: dict[str, Any]) -> dict[str, Any]:
    providers = config.get("providers") if isinstance(config.get("providers"), dict) else {}
    provider = providers.get(name)
    if not isinstance(provider, dict):
        if name == "prompt-only":
            return {"mode": "prompt-only"}
        raise SystemExit(f"Unknown agent provider: {name}")
    return provider


def resolve_auto_provider(
    config: dict[str, Any], provider: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    priority = provider.get("priority")
    if not isinstance(priority, list) or not priority:
        priority = ["codex-cli", "claude-code", "prompt-only"]
    probe_args = argparse.Namespace(argv=[], command="")
    for candidate in priority:
        candidate_name = str(candidate)
        candidate_provider = provider_by_name(candidate_name, config)
        mode = str(candidate_provider.get("mode", "prompt-only"))
        if mode == "prompt-only":
            return candidate_name, candidate_provider
        if mode == "command" and command_available(command_argv(probe_args, candidate_provider)):
            return candidate_name, candidate_provider
    return "prompt-only", {"mode": "prompt-only"}


def active_provider(
    args: argparse.Namespace, config: dict[str, Any]
) -> tuple[str, dict[str, Any], str]:
    command_supplied = bool(args.argv or args.command or os.environ.get("AGENT_COMMAND"))
    provider_name = (
        args.provider
        or os.environ.get("AGENT_PROVIDER")
        or ("command" if command_supplied else str(config.get("active_provider") or "prompt-only"))
    )
    provider = provider_by_name(provider_name, config)
    if str(provider.get("mode", "prompt-only")) == "auto" and not command_supplied:
        resolved_name, resolved_provider = resolve_auto_provider(config, provider)
        return provider_name, resolved_provider, resolved_name
    return provider_name, provider, provider_name


def write_run_record(record: dict[str, Any], stdout: str) -> Path:
    report_dir = ROOT / "reports" / "agent-runs"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{record['id']}.json"
    payload = dict(record)
    payload["stdout"] = stdout
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def update_state(record: dict[str, Any], report_path: Path) -> None:
    state = load_state()
    rel = str(report_path.relative_to(ROOT))
    state.setdefault("agent_runs", []).append(rel)
    adapter_state = state.setdefault("agent_adapter", {})
    if not isinstance(adapter_state, dict):
        adapter_state = {}
        state["agent_adapter"] = adapter_state
    adapter_state.update(
        {
            "last_provider": record["provider"],
            "last_resolved_provider": record["resolved_provider"],
            "last_mode": record["mode"],
            "last_role": record["role"],
            "last_exit_code": record["exit_code"],
            "last_run_at": record["completed_at"],
            "last_report": rel,
        }
    )
    save_state(state)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True)
    parser.add_argument("--prompt-file", default="")
    parser.add_argument("--provider", default="")
    parser.add_argument(
        "--command", default="", help="Command string parsed with shlex; prompt is sent on stdin."
    )
    parser.add_argument(
        "--argv", action="append", default=[], help="Exact argv element. Repeat for each argument."
    )
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument(
        "--resolve-only",
        action="store_true",
        help="Resolve the active provider without invoking it.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_json(CONFIG_FILE, {})
    if not isinstance(config, dict):
        config = {}
    prompt, prompt_source = read_prompt(args)
    provider_name, provider, resolved_provider_name = active_provider(args, config)
    mode = str(provider.get("mode", "prompt-only"))
    timeout = args.timeout_seconds
    if timeout is None:
        timeout = float(
            provider.get("timeout_seconds", config.get("default_timeout_seconds", 0)) or 0
        )

    stdout = ""
    stderr = ""
    exit_code = 0
    argv = command_argv(args, provider)
    started = now()

    if args.resolve_only:
        stdout = f"Provider resolved: {provider_name} -> {resolved_provider_name}\n"
    elif mode == "prompt-only" or not argv:
        stdout = f"Prompt prepared: {prompt_source}\nSet AGENT_COMMAND, AGENT_PROVIDER, --command, or --argv to invoke an agent runtime.\n"
    else:
        try:
            result = subprocess.run(
                argv,
                cwd=ROOT.parent,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout if timeout and timeout > 0 else None,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout = exc.stdout or ""
            stderr = f"Timed out after {timeout} seconds."
        except OSError as exc:
            exit_code = 127
            stderr = str(exc)
        else:
            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr

    completed = now()
    record = {
        "id": f"{compact_ts()}-agent-adapter-{args.role}",
        "role": args.role,
        "provider": provider_name,
        "resolved_provider": resolved_provider_name,
        "mode": mode,
        "prompt_source": prompt_source,
        "command_configured": bool(argv),
        "argv": argv,
        "started_at": started,
        "completed_at": completed,
        "exit_code": exit_code,
        "stderr": stderr,
    }
    report_path = write_run_record(record, stdout)
    update_state(record, report_path)
    log_event(
        "Agent Adapter",
        "completed",
        f"role={args.role} provider={provider_name} resolved={resolved_provider_name} exit={exit_code}",
    )

    if args.json:
        output = dict(record)
        output["report_path"] = str(report_path)
        output["stdout"] = stdout
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(stdout, end="")
        if stderr:
            print(stderr, file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
