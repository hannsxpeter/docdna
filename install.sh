#!/usr/bin/env sh
# Install the docdna skill into supported coding-agent skill directories.
# Implements: P-MUST-05
#
# Usage:
#   ./install.sh <all|target>
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
PYTHON="${PYTHON:-python3}"
SUPPORTED_TARGETS=$(
  "$PYTHON" - "$SRC_DIR/skill" <<'PY'
import os
import sys

sys.dont_write_bytecode = True
skill_root = sys.argv[1]
sys.path.insert(0, os.path.join(skill_root, "scripts"))
from docdna_runtime import RuntimeRegistryError, install_metadata, load_registry

try:
    rows = install_metadata(load_registry(skill_root))
except RuntimeRegistryError as error:
    sys.stderr.write("install.sh: invalid runtime registry: %s\n" % error)
    raise SystemExit(2)
print(" ".join(row["selector"] for row in rows))
PY
)

install_skill() {
  label=$1
  skill_dest=$2
  stale_file=$3

  rm -rf "$skill_dest"
  mkdir -p "$skill_dest"
  cp -R "$SRC_DIR/skill/." "$skill_dest/"
  find "$skill_dest/scripts" -name '*.py' -exec chmod +x {} +
  find "$skill_dest" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

  if [ -n "$stale_file" ] && [ -f "$stale_file" ]; then
    rm -f "$stale_file"
    printf 'Removed stale bare-file install at %s\n' "$stale_file"
  fi

  printf 'Installed docdna v%s for %s to %s\n' "$VERSION" "$label" "$skill_dest"
}

registry_metadata() {
  "$PYTHON" - "$SRC_DIR/skill" "$1" <<'PY'
import os
import sys

sys.dont_write_bytecode = True
skill_root, selector = sys.argv[1:]
sys.path.insert(0, os.path.join(skill_root, "scripts"))
from docdna_runtime import RuntimeRegistryError, install_metadata, load_registry

try:
    metadata = install_metadata(load_registry(skill_root))
except RuntimeRegistryError as error:
    sys.stderr.write("install.sh: invalid runtime registry: %s\n" % error)
    raise SystemExit(2)
rows = [row for row in metadata if row["selector"] == selector]
if len(rows) != 1:
    raise SystemExit("install selector is not uniquely registered: %s" % selector)
print(rows[0]["label"])
print(rows[0]["default_location"])
PY
}

default_destination() {
  case "$1" in
    \~/*)
      relative=${1#\~/}
      printf '%s/%s\n' "${HOME%/}" "$relative"
      ;;
    *)
      echo "install.sh: registry default is not home-relative" >&2
      exit 2
      ;;
  esac
}

override_destination() {
  selector=$1
  registry_default=$2
  case "$selector" in
    claude)
      if [ -n "${CLAUDE_SKILLS_DIR:-}" ]; then
        printf '%s/docdna\n' "${CLAUDE_SKILLS_DIR%/}"
      else
        default_destination "$registry_default"
      fi
      ;;
    codex)
      if [ -n "${CODEX_SKILLS_DIR:-}" ]; then
        printf '%s/docdna\n' "${CODEX_SKILLS_DIR%/}"
      elif [ -n "${CODEX_HOME:-}" ]; then
        printf '%s/skills/docdna\n' "${CODEX_HOME%/}"
      else
        default_destination "$registry_default"
      fi
      ;;
    cursor)
      if [ -n "${CURSOR_SKILLS_DIR:-}" ]; then
        printf '%s/docdna\n' "${CURSOR_SKILLS_DIR%/}"
      else
        default_destination "$registry_default"
      fi
      ;;
    windsurf)
      if [ -n "${WINDSURF_SKILLS_DIR:-}" ]; then
        printf '%s/docdna\n' "${WINDSURF_SKILLS_DIR%/}"
      else
        default_destination "$registry_default"
      fi
      ;;
    *)
      default_destination "$registry_default"
      ;;
  esac
}

stale_file_for() {
  case "$1" in
    claude | codex)
      printf '%s\n' "${2%/docdna}/docdna.md"
      ;;
    *)
      printf '\n'
      ;;
  esac
}

install_target() {
  metadata=$(registry_metadata "$1")
  label=$(printf '%s\n' "$metadata" | sed -n '1p')
  registry_default=$(printf '%s\n' "$metadata" | sed -n '2p')
  skill_dest=$(override_destination "$1" "$registry_default")
  stale_file=$(stale_file_for "$1" "$skill_dest")
  install_skill "$label" "$skill_dest" "$stale_file"
}

is_supported_target() {
  for supported_target in $SUPPORTED_TARGETS; do
    if [ "$1" = "$supported_target" ]; then
      return 0
    fi
  done
  return 1
}

usage() {
  echo "Usage: ./install.sh <all|target>" >&2
  echo "" >&2
  echo "Targets:" >&2
  echo "  all       Install every registry-supported target" >&2
  for supported_target in $SUPPORTED_TARGETS; do
    metadata=$(registry_metadata "$supported_target")
    label=$(printf '%s\n' "$metadata" | sed -n '1p')
    printf '  %-9s Install for %s\n' "$supported_target" "$label" >&2
  done
}

if [ "$TARGET" = "cascade" ]; then
  TARGET="windsurf"
fi

case "$TARGET" in
  "")
    usage
    exit 0
    ;;
  all)
    for supported_target in $SUPPORTED_TARGETS; do
      install_target "$supported_target"
    done
    ;;
  *)
    if ! is_supported_target "$TARGET"; then
      usage
      exit 2
    fi
    install_target "$TARGET"
    ;;
esac

echo "Restart the target coding agent to pick it up."
