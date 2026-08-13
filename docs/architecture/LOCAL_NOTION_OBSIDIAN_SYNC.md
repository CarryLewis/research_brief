# Local Notion → Obsidian (iCloud Thinking valut)

**Goal:** Notion Thinking database writes **directly** into your Mac Obsidian vault (iCloud), without waiting on GitHub `rsync`.

```text
Notion Thinking DB
        ↓  Notion API (on your Mac)
python -m app.cli.thinking_sync --vault "$OBSIDIAN_VAULT"
        ↓
OBSIDIAN_VAULT/Thinking/*.md   ← opened by Obsidian “Thinking valut”
```

GitHub Actions can still update the **repo** `vault/` for backup / Quartz. That path is separate from your iCloud Obsidian vault.

## One-time Mac setup

### 1. Confirm vault path

Obsidian → bottom-left vault name → **Manage vaults** → copy the path for **Thinking valut**.

Typical iCloud layout:

```text
/Users/carrylewis/Library/Mobile Documents/iCloud~md~obsidian/Documents/Thinking valut
```

If Manage vaults shows only `.../Documents` (no `Thinking valut` suffix), use that exact path instead.

### 2. Pull latest scripts

```bash
cd ~/Documents/research_brief
git pull
```

### 3. Put Notion secrets in repo `.env` (gitignored)

```bash
cat > ~/Documents/research_brief/.env <<'EOF'
NOTION_TOKEN=ntn_your_token_here
NOTION_THINKING_DATABASE_ID=51e7fdfd-46f8-4d85-a813-f68b56131615
EOF
```

### 4. Manual direct sync (verify)

```bash
export OBSIDIAN_VAULT="/Users/carrylewis/Library/Mobile Documents/iCloud~md~obsidian/Documents/Thinking valut"
# or the exact Manage vaults path

chmod +x ~/Documents/research_brief/scripts/sync-to-local-obsidian.sh
~/Documents/research_brief/scripts/sync-to-local-obsidian.sh
tail -40 ~/Library/Logs/thinking-vault-sync.log
```

Then open Obsidian → `Thinking/`.

### 5. Auto every 15 minutes

```bash
mkdir -p ~/Library/LaunchAgents
cp ~/Documents/research_brief/scripts/macos/com.carrylewis.thinking-vault-sync.plist.example \
   ~/Library/LaunchAgents/com.carrylewis.thinking-vault-sync.plist

# Edit OBSIDIAN_VAULT in the plist if your Manage vaults path differs

launchctl bootout gui/$(id -u)/com.carrylewis.thinking-vault-sync 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.carrylewis.thinking-vault-sync.plist
launchctl kickstart -k gui/$(id -u)/com.carrylewis.thinking-vault-sync
```

## Notes

- Sync **overwrites** Notion-linked notes under `Thinking/` by `source_id`.
- SQLite sync state lives in `~/Documents/research_brief/data/` (not in iCloud).
- Do not `git init` inside the iCloud Obsidian folder.
- If `git` / Notion fail with `127.0.0.1:7890`, turn off the proxy or keep it cleared (the script clears common proxy env vars).
