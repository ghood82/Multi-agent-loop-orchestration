#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
role="${1:-}"
branch="${2:-}"

if [[ -z "$role" || -z "$branch" ]]; then
  echo "Usage: create-worktree.sh <role> <branch>" >&2
  exit 2
fi

repo_root="$(git -C "$ROOT_DIR" rev-parse --show-toplevel)"
safe_role="$(printf '%s' "$role" | tr -c 'A-Za-z0-9._-' '-')"
safe_branch="$(printf '%s' "$branch" | tr -c 'A-Za-z0-9._-' '-')"
worktree_path="${ROOT_DIR}/worktrees/${safe_role}-${safe_branch}"

if [[ -e "$worktree_path" ]]; then
  echo "Worktree already exists: $worktree_path" >&2
  exit 1
fi

mkdir -p "${ROOT_DIR}/worktrees"
git -C "$repo_root" worktree add -b "$branch" "$worktree_path"
python3 "${ROOT_DIR}/bin/update-state.py" set "worktrees.${safe_role}" "\"${worktree_path}\""
echo "$worktree_path"
