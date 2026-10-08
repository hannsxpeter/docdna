#!/usr/bin/env sh
# Install the docdna skill into supported coding-agent skill directories.
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
TAB=$(printf '\t')

# Load and validate the registry once. Each line is selector, label, and default location,
# separated by tabs; the registry validator rejects control characters in all three.
REGISTRY_ROWS=$(
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
for row in rows:
    print("\t".join((row["selector"], row["label"], row["default_location"])))
PY
)

# Set only while one install is in flight, so the EXIT trap can put the previous install back
# and remove the staging directory if anything fails before the swap completes.
INSTALL_WORK=
INSTALL_DEST=

cleanup_install() {
  if [ -z "$INSTALL_WORK" ]; then
    return 0
  fi
  if { [ -e "$INSTALL_WORK/old" ] || [ -L "$INSTALL_WORK/old" ]; } \
      && [ ! -e "$INSTALL_DEST" ] && [ ! -L "$INSTALL_DEST" ]; then
    if mv -- "$INSTALL_WORK/old" "$INSTALL_DEST"; then
      printf 'install.sh: restored the previous install at %s\n' "$INSTALL_DEST" >&2
    else
      printf 'install.sh: previous install kept at %s\n' "$INSTALL_WORK/old" >&2
      INSTALL_WORK=
      return 0
    fi
  fi
  rm -rf -- "$INSTALL_WORK" || :
  INSTALL_WORK=
}

trap cleanup_install EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

registry_selectors() {
  printf '%s\n' "$REGISTRY_ROWS" | while IFS=$TAB read -r listed_selector _ _; do
    if [ -n "$listed_selector" ]; then
      printf '%s\n' "$listed_selector"
    fi
  done
}

registry_field() {
  printf '%s\n' "$REGISTRY_ROWS" | while IFS=$TAB read -r row_selector row_label row_default; do
    if [ "$row_selector" = "$1" ]; then
      case "$2" in
        label) printf '%s\n' "$row_label" ;;
        default) printf '%s\n' "$row_default" ;;
      esac
    fi
  done
}

# Exit 3 when the destination is the source checkout or one of its ancestors, 0 when it is not.
# Inode identity, unlike a path prefix, also holds on a case-insensitive filesystem.
destination_holds_source() {
  "$PYTHON" - "$1" "$SRC_DIR" <<'PY'
import os
import sys

destination, source = sys.argv[1:]
try:
    target = os.lstat(destination)
    current = os.path.realpath(source)
    while True:
        details = os.stat(current)
        if (details.st_dev, details.st_ino) == (target.st_dev, target.st_ino):
            raise SystemExit(3)
        parent = os.path.dirname(current)
        if parent == current:
            raise SystemExit(0)
        current = parent
except OSError as error:
    sys.stderr.write("install.sh: could not inspect %s: %s\n" % (destination, error))
    raise SystemExit(4)
PY
}

install_skill() {
  label=$1
  skill_dest=$2
  stale_file=$3

  if [ -e "$skill_dest" ] || [ -L "$skill_dest" ]; then
    holds_source=0
    destination_holds_source "$skill_dest" || holds_source=$?
    if [ "$holds_source" -eq 3 ]; then
      printf 'install.sh: refusing to replace %s, which contains this source checkout\n' \
        "$skill_dest" >&2
      exit 2
    elif [ "$holds_source" -ne 0 ]; then
      exit 2
    fi
  fi

  # Stage beside the destination so the final mv is a same-filesystem rename.
  dest_parent=$(dirname -- "$skill_dest")
  mkdir -p -- "$dest_parent"
  work="$dest_parent/.$(basename -- "$skill_dest").install.$$"
  mkdir -- "$work"
  INSTALL_WORK=$work
  INSTALL_DEST=$skill_dest
  mkdir -- "$work/new"
  cp -R "$SRC_DIR/skill/." "$work/new/"
  find "$work/new" -name '__pycache__' -type d -prune -exec rm -rf {} +
  find "$work/new/scripts" -name '*.py' -exec chmod +x {} +
  if ! report=$(PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$work/new/scripts/docdna_doctor.py" \
      --skill-root "$work/new"); then
    printf '%s\n' "$report" >&2
    printf 'install.sh: staged copy failed docdna_doctor; %s left unchanged\n' "$skill_dest" >&2
    exit 1
  fi

  # Keep the old install until the new one is in place; the EXIT trap restores it on failure.
  if [ -e "$skill_dest" ] || [ -L "$skill_dest" ]; then
    mv -- "$skill_dest" "$work/old"
  fi
  mv -- "$work/new" "$skill_dest"
  INSTALL_WORK=
  rm -rf -- "$work" || printf 'install.sh: could not remove %s\n' "$work" >&2

  if [ -n "$stale_file" ] && [ -f "$stale_file" ]; then
    rm -f "$stale_file"
    printf 'Removed stale bare-file install at %s\n' "$stale_file"
  fi

  printf 'Installed docdna v%s for %s to %s\n' "$VERSION" "$label" "$skill_dest"
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
  label=$(registry_field "$1" label)
  registry_default=$(registry_field "$1" default)
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
  printf '%s\n' "$REGISTRY_ROWS" | while IFS=$TAB read -r usage_selector usage_label _; do
    if [ -n "$usage_selector" ]; then
      printf '  %-9s Install for %s\n' "$usage_selector" "$usage_label" >&2
    fi
  done
}

SUPPORTED_TARGETS=$(registry_selectors)

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
