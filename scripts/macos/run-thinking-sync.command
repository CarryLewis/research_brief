#!/bin/bash
# Double-clickable / Shortcuts-friendly wrapper for Notion → Obsidian sync.
set -euo pipefail
export RESEARCH_BRIEF_REPO="${RESEARCH_BRIEF_REPO:-$HOME/Documents/research_brief}"
export OBSIDIAN_VAULT="${OBSIDIAN_VAULT:-$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents}"
exec /bin/bash "$RESEARCH_BRIEF_REPO/scripts/sync-to-local-obsidian.sh"
