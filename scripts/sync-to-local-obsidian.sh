#!/usr/bin/env bash
# Pull Notion→GitHub Thinking notes, then mirror vault/Thinking into a local Obsidian vault.
#
# Required (env or defaults below):
#   RESEARCH_BRIEF_REPO  — clone of this GitHub repo
#   OBSIDIAN_VAULT       — Obsidian vault root (the folder Obsidian opened)
#
# Optional:
#   THINKING_SUBDIR      — destination under vault (default: Thinking)
#   RSYNC_DELETE=1       — mirror exactly (default); set 0 to keep local-only files
#   SYNC_LOG             — append log file (default: ~/Library/Logs/thinking-vault-sync.log on macOS)

set -euo pipefail

REPO="${RESEARCH_BRIEF_REPO:-$HOME/Documents/research_brief}"
VAULT="${OBSIDIAN_VAULT:-$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents}"
SUBDIR="${THINKING_SUBDIR:-Thinking}"
RSYNC_DELETE="${RSYNC_DELETE:-1}"

if [[ "$(uname -s)" == "Darwin" ]]; then
  LOG="${SYNC_LOG:-$HOME/Library/Logs/thinking-vault-sync.log}"
else
  LOG="${SYNC_LOG:-$HOME/.cache/thinking-vault-sync.log}"
fi

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) thinking-vault local sync ===="

if [[ ! -d "$REPO/.git" ]]; then
  echo "ERROR: not a git repo: $REPO" >&2
  echo "Clone first: git clone https://github.com/CarryLewis/research_brief.git \"$REPO\"" >&2
  exit 1
fi

if [[ ! -d "$VAULT" ]]; then
  echo "ERROR: Obsidian vault not found: $VAULT" >&2
  exit 1
fi

SRC="$REPO/vault/Thinking"
DST="$VAULT/$SUBDIR"

if [[ ! -d "$SRC" ]]; then
  echo "ERROR: missing $SRC (pull the repo / wait for Actions sync)" >&2
  exit 1
fi

echo "repo=$REPO"
echo "vault=$VAULT"
echo "src=$SRC -> dst=$DST"

cd "$REPO"
# Avoid stale Clash/Surge proxy (127.0.0.1:7890) breaking unattended runs
export http_proxy="" https_proxy="" HTTP_PROXY="" HTTPS_PROXY="" ALL_PROXY="" all_proxy=""
git -c http.proxy= -c https.proxy= fetch origin main
git -c http.proxy= -c https.proxy= pull --ff-only origin main

mkdir -p "$DST"
RSYNC_ARGS=(-a)
if [[ "$RSYNC_DELETE" == "1" ]]; then
  RSYNC_ARGS+=(--delete)
fi
# Keep Obsidian / Finder junk out of the mirror source side; destination may still have them.
rsync "${RSYNC_ARGS[@]}" \
  --exclude '.DS_Store' \
  --exclude '.obsidian' \
  "$SRC/" "$DST/"

echo "OK: synced Thinking -> $DST"
echo
