#!/usr/bin/env python3
"""Create a reusable multi-agent orchestration harness in a target repo."""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


PLACEHOLDER_DEFAULTS = {
    "PROJECT_NAME": "TBD",
    "REPO_NAME": "TBD",
    "ROADMAP_NAME": "TBD",
    "CURRENT_PHASE": "TBD",
    "CURRENT_OBJECTIVE": "TBD",
    "STATE_FILE_PATH": "docs/project-roadmap-state.md",
    "TEST_COMMAND": "TBD",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an orchestration runtime harness in a software project."
    )
    parser.add_argument(
        "--target",
        default=".",
        help="Target repository root. Defaults to current directory.",
    )
    parser.add_argument("--project-name", default=PLACEHOLDER_DEFAULTS["PROJECT_NAME"])
    parser.add_argument("--repo-name", default=PLACEHOLDER_DEFAULTS["REPO_NAME"])
    parser.add_argument("--roadmap-name", default=PLACEHOLDER_DEFAULTS["ROADMAP_NAME"])
    parser.add_argument("--current-phase", default=PLACEHOLDER_DEFAULTS["CURRENT_PHASE"])
    parser.add_argument(
        "--current-objective", default=PLACEHOLDER_DEFAULTS["CURRENT_OBJECTIVE"]
    )
    parser.add_argument(
        "--state-file-path", default=PLACEHOLDER_DEFAULTS["STATE_FILE_PATH"]
    )
    parser.add_argument("--test-command", default=PLACEHOLDER_DEFAULTS["TEST_COMMAND"])
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing harness files.",
    )
    return parser.parse_args()


def replacements(args: argparse.Namespace) -> dict[str, str]:
    values = {
        "PROJECT_NAME": args.project_name,
        "REPO_NAME": args.repo_name,
        "ROADMAP_NAME": args.roadmap_name,
        "CURRENT_PHASE": args.current_phase,
        "CURRENT_OBJECTIVE": args.current_objective,
        "STATE_FILE_PATH": args.state_file_path,
        "TEST_COMMAND": args.test_command,
        "CREATED_AT": datetime.now(timezone.utc).isoformat(),
    }
    return {f"{{{{{key}}}}}": value for key, value in values.items()}


def render_text(text: str, values: dict[str, str]) -> str:
    for placeholder, value in values.items():
        text = text.replace(placeholder, value)
    return text


def should_skip(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}


def copy_template(template_root: Path, target_root: Path, values: dict[str, str], force: bool) -> list[Path]:
    created: list[Path] = []
    for src in sorted(template_root.rglob("*")):
        if should_skip(src.relative_to(template_root)):
            continue
        rel = src.relative_to(template_root)
        dest = target_root / rel
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        if dest.exists() and not force:
            raise FileExistsError(
                f"{dest} already exists. Re-run with --force to overwrite it."
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            rendered = render_text(src.read_text(), values)
        except UnicodeDecodeError:
            shutil.copy2(src, dest)
        else:
            dest.write_text(rendered)
        if dest.suffix in {".sh", ".py"}:
            dest.chmod(dest.stat().st_mode | 0o111)
        created.append(dest)
    return created


def main() -> int:
    args = parse_args()
    skill_root = Path(__file__).resolve().parents[1]
    template_root = skill_root / "assets" / "runtime-harness"
    if not template_root.exists():
        raise SystemExit(f"Template folder not found: {template_root}")

    target_root = Path(args.target).resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    created = copy_template(template_root, target_root, replacements(args), args.force)

    print(f"Created orchestration harness in {target_root}")
    for path in created:
        print(f"- {path.relative_to(target_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
