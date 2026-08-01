#!/usr/bin/env sh
# Install the docdna skill into supported coding-agent skill directories.
#
# Usage:
#   ./install.sh <all|claude|codex|cursor|windsurf>
#
# Override destinations with:
#   CLAUDE_SKILLS_DIR=/path/to/skills ./install.sh claude
#   CODEX_SKILLS_DIR=/path/to/skills ./install.sh codex
#   CURSOR_SKILLS_DIR=/path/to/skills ./install.sh cursor
#   WINDSURF_SKILLS_DIR=/path/to/skills ./install.sh windsurf

set -eu

unset CDPATH
SRC_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
VERSION=$(awk '/^Version: / { print $2; exit }' "$SRC_DIR/skill/SKILL.md")
TARGET="${1:-}"

install_skill() {
  label=$1
  dest=$2
  stale_file=$3
  skill_dest="$dest/docdna"

  rm -rf "$skill_dest"
  mkdir -p "$skill_dest"
  cp -R "$SRC_DIR/skill/." "$skill_dest/"
  find "$skill_dest/scripts" -name '*.py' -exec chmod +x {} +
  find "$skill_dest" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

  if [ -n "$stale_file" ] && [ -f "$stale_file" ]; then
    rm -f "$stale_file"
    echo "Removed stale bare-file install at $stale_file"
  fi

  echo "Installed docdna v$VERSION for $label to $skill_dest"
}

usage() {
  echo "Usage: ./install.sh <all|claude|codex|cursor|windsurf>" >&2
  echo "" >&2
  echo "Targets:" >&2
  echo "  all       Install for Claude Code, Codex, Cursor, and Windsurf/Cascade" >&2
  echo "  claude    Install for Claude Code" >&2
  echo "  codex     Install for Codex" >&2
  echo "  cursor    Install for Cursor" >&2
  echo "  windsurf  Install for Windsurf/Cascade" >&2
}

case "$TARGET" in
  "")
    usage
    exit 0
    ;;
  all)
    claude_dest="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
    codex_dest="${CODEX_SKILLS_DIR:-${CODEX_HOME:-$HOME/.codex}/skills}"
    cursor_dest="${CURSOR_SKILLS_DIR:-$HOME/.cursor/skills}"
    windsurf_dest="${WINDSURF_SKILLS_DIR:-$HOME/.codeium/windsurf/skills}"
    install_skill "Claude Code" "$claude_dest" "$claude_dest/docdna.md"
    install_skill "Codex" "$codex_dest" "$codex_dest/docdna.md"
    install_skill "Cursor" "$cursor_dest" ""
    install_skill "Windsurf/Cascade" "$windsurf_dest" ""
    ;;
  claude)
    claude_dest="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
    install_skill "Claude Code" "$claude_dest" "$claude_dest/docdna.md"
    ;;
  codex)
    codex_dest="${CODEX_SKILLS_DIR:-${CODEX_HOME:-$HOME/.codex}/skills}"
    install_skill "Codex" "$codex_dest" "$codex_dest/docdna.md"
    ;;
  cursor)
    cursor_dest="${CURSOR_SKILLS_DIR:-$HOME/.cursor/skills}"
    install_skill "Cursor" "$cursor_dest" ""
    ;;
  windsurf | cascade)
    windsurf_dest="${WINDSURF_SKILLS_DIR:-$HOME/.codeium/windsurf/skills}"
    install_skill "Windsurf/Cascade" "$windsurf_dest" ""
    ;;
  *)
    usage
    exit 2
    ;;
esac

echo "Restart the target coding agent to pick it up."
