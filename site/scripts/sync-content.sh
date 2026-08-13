#!/usr/bin/env bash
# Sync repo vault/ → site/content/ for Quartz (portable; no rsync required).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VAULT="${QUARTZ_VAULT_PATH:-$ROOT/vault}"
CONTENT="$ROOT/site/content"

if [ ! -d "$VAULT" ]; then
  echo "Vault not found: $VAULT" >&2
  exit 1
fi

mkdir -p "$CONTENT"

# Wipe generated content but keep .gitignore / .gitkeep
find "$CONTENT" -mindepth 1 \
  ! -name '.gitignore' \
  ! -name '.gitkeep' \
  -exec rm -rf {} + 2>/dev/null || true

mkdir -p "$CONTENT"

python3 - "$VAULT" "$CONTENT" <<'PY'
import os
import shutil
import sys
from pathlib import Path

vault = Path(sys.argv[1])
content = Path(sys.argv[2])

SKIP_DIR_NAMES = {".obsidian", ".git", "Archive", "90_Meta"}
SKIP_FILE_NAMES = {".DS_Store", ".thinking-folder"}


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or name.startswith(".")


copied = 0
for root, dirs, files in os.walk(vault):
    Path(root).relative_to(vault)  # validate under vault
    dirs[:] = [d for d in dirs if not should_skip_dir(d)]
    rel = Path(root).relative_to(vault)
    dest_root = content / rel
    dest_root.mkdir(parents=True, exist_ok=True)
    for name in files:
        if name in SKIP_FILE_NAMES or name.startswith("."):
            continue
        src = Path(root) / name
        dst = dest_root / name
        shutil.copy2(src, dst)
        copied += 1

print(f"Copied {copied} files from {vault} → {content}")
PY

if [ -f "$CONTENT/Welcome.md" ] && [ ! -f "$CONTENT/index.md" ]; then
  cp "$CONTENT/Welcome.md" "$CONTENT/index.md"
fi

if [ ! -f "$CONTENT/index.md" ]; then
  cat > "$CONTENT/index.md" <<'EOF'
---
title: Thinking Garden
---

# Thinking Garden

Public mirror of the Obsidian vault (Quartz).

Browse via search, explorer, graph, and backlinks.
EOF
fi

echo "Synced $VAULT → $CONTENT"
