#!/usr/bin/env bash
# Links every skill in ./skills into ~/.claude/skills, so every Claude Code
# session on this machine can use it. Links (not copies) mean edits in this
# repo take effect straight away. Safe to re-run; never overwrites anything.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target_dir="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$target_dir"

for skill in "$repo_dir"/skills/*/; do
  [ -f "${skill}SKILL.md" ] || continue
  src="${skill%/}"
  name="$(basename "$src")"
  dest="$target_dir/$name"

  if [ -L "$dest" ]; then
    if [ "$(readlink "$dest")" = "$src" ]; then
      echo "ok      $name (already linked)"
    else
      echo "skip    $name: $dest already links to $(readlink "$dest")" >&2
    fi
  elif [ -e "$dest" ]; then
    echo "skip    $name: $dest already exists and is not a link" >&2
  else
    ln -s "$src" "$dest"
    echo "linked  $name -> $src"
  fi
done
