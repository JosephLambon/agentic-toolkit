#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
client="claude"
if [ "$#" -gt 0 ]; then
  if [ "$#" -ne 2 ] || [ "$1" != "--client" ]; then
    echo "usage: install.sh [--client claude|copilot|both]" >&2
    exit 2
  fi
  client="$2"
fi
case "$client" in
  claude|copilot|both) ;;
  *) echo "unknown client: $client (expected claude, copilot or both)" >&2; exit 2 ;;
esac

link_skills() {
  local target_dir="$1" skill src name dest
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
}

if [ "$client" = "claude" ] || [ "$client" = "both" ]; then
  link_skills "${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
fi
if [ "$client" = "copilot" ] || [ "$client" = "both" ]; then
  link_skills "${COPILOT_SKILLS_DIR:-${COPILOT_HOME:-$HOME/.copilot}/skills}"
fi
