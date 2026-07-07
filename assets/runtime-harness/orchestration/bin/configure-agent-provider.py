#!/usr/bin/env python3
"""Configure the provider used by agent-adapter.py."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "agent-adapter.json"
STATE_FILE = ROOT / "state.json"
EVENT_LOG = ROOT / "events.log"

BUILTIN_PROVIDERS: dict[str, dict[str, Any]] = {
    "auto": {
        "mode": "auto",
        "priority": ["codex-cli", "claude-code", "prompt-only"],
        "description": "Automatically use Codex CLI when installed, then Claude Code, then prompt-only.",
    },
    "prompt-only": {
        "mode": "prompt-only",
        "description": "Prepare prompts and record adapter runs without invoking an external agent.",
    },
    "command": {
        "mode": "command",
        "description": "Run AGENT_COMMAND or --command as argv parsed with shlex; prompt is sent on stdin.",
    },
    "codex-cli": {
        "mode": "command",
        "command": "codex exec",
        "description": "Use a locally installed Codex CLI command. Override command if your CLI invocation differs.",
    },
    "claude-code": {
        "mode": "command",
        "command": "claude -p",
        "description": "Use a locally installed Claude Code command in non-interactive print mode. Override command if your CLI invocation differs.",
    },
    "codex-subagent": {
        "mode": "prompt-only",
        "description": "Prepare prompts for Codex Desktop or MCP subagent dispatch. Set command only if a local subagent CLI bridge exists.",
    },
    "custom-command": {
        "mode": "command",
        "command": "",
        "description": "Operator-supplied command parsed with shlex; prompt is sent on stdin.",
    },
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_config() -> dict[str, Any]:
    config = load_json(CONFIG_FILE, {})
    if not isinstance(config, dict):
        config = {}
    config.setdefault("version", 1)
    config.setdefault("active_provider", "auto")
    config.setdefault("default_timeout_seconds", 0)
    providers = config.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        config["providers"] = providers
    for name, provider in BUILTIN_PROVIDERS.items():
        providers.setdefault(name, provider)
    return config


def load_state() -> dict[str, Any]:
    state = load_json(STATE_FILE, {})
    return state if isinstance(state, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    save_json(STATE_FILE, state)


def log_event(event: str, note: str = "") -> None:
    entry = {"ts": now(), "role": "configure-agent-provider", "event": event, "note": note}
    with EVENT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def provider_config(args: argparse.Namespace, existing: dict[str, Any]) -> dict[str, Any]:
    provider = dict(existing)
    if args.mode:
        provider["mode"] = args.mode
    if args.command is not None:
        provider["command"] = args.command
    if args.timeout_seconds is not None:
        provider["timeout_seconds"] = args.timeout_seconds
    if args.description:
        provider["description"] = args.description
    if (
        args.provider == "custom-command"
        and not provider.get("command")
        and provider.get("mode") == "command"
    ):
        raise SystemExit("--command is required when configuring custom-command in command mode.")
    return provider


def configure(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config()
    providers = config["providers"]
    if args.provider not in providers:
        raise SystemExit(f"Unknown provider: {args.provider}")
    providers[args.provider] = provider_config(args, providers[args.provider])
    config["active_provider"] = args.provider
    if args.default_timeout_seconds is not None:
        config["default_timeout_seconds"] = args.default_timeout_seconds
    config["last_configured_at"] = now()
    config["last_configured_provider"] = args.provider
    save_json(CONFIG_FILE, config)

    state = load_state()
    state.setdefault("agent_adapter", {})
    state["agent_adapter"].update(
        {
            "configured_provider": args.provider,
            "configured_mode": providers[args.provider].get("mode", "prompt-only"),
            "configured_command": providers[args.provider].get("command", ""),
            "configured_at": config["last_configured_at"],
        }
    )
    save_state(state)
    log_event("configured", args.provider)
    return config


def run_test(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "bin" / "agent-adapter.py"),
        "--role",
        "provider-test",
        "--prompt-file",
        args.test_prompt,
        "--json",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = {"stdout": result.stdout}
    return {"exit_code": result.returncode, "result": parsed}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=sorted(BUILTIN_PROVIDERS), default="prompt-only")
    parser.add_argument("--mode", choices=["auto", "prompt-only", "command"])
    parser.add_argument("--command")
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--default-timeout-seconds", type=float)
    parser.add_argument("--description")
    parser.add_argument("--list", action="store_true", help="List configured providers and exit.")
    parser.add_argument(
        "--test", action="store_true", help="Run agent-adapter.py after configuring."
    )
    parser.add_argument("--test-prompt", default="orchestration/README.md")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list:
        config = load_config()
        if args.json:
            print(json.dumps(config, indent=2, sort_keys=True))
        else:
            print(f"Active provider: {config.get('active_provider', 'prompt-only')}")
            for name, provider in sorted(config.get("providers", {}).items()):
                print(
                    f"- {name}: {provider.get('mode', 'prompt-only')} {provider.get('command', '')}".rstrip()
                )
        return 0

    config = configure(args)
    test_result = run_test(args) if args.test else None
    if args.json:
        print(json.dumps({"config": config, "test": test_result}, indent=2, sort_keys=True))
    else:
        provider = config["providers"][args.provider]
        print(f"Agent provider configured: {args.provider}")
        print(f"Mode: {provider.get('mode', 'prompt-only')}")
        if provider.get("command"):
            print(f"Command: {provider['command']}")
        if test_result:
            print(f"Test exit code: {test_result['exit_code']}")
    if test_result and test_result["exit_code"] != 0:
        return int(test_result["exit_code"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
