# Local Notion → Obsidian (iCloud Thinking valut)

**Goal:** Notion Thinking database writes **directly** into your Mac Obsidian vault (iCloud). GitHub Actions can still keep a separate repo backup.

## Dual pipeline

```text
                         ┌─ (A) Mac script / LaunchAgent ──► iCloud Obsidian “Thinking valut”
Notion Thinking DB ──────┤
                         └─ (B) GitHub Actions (hourly) ───► repo vault/  (backup + Quartz)
```

| Path | Destination | Purpose |
|------|-------------|---------|
| **A — local** | iCloud Obsidian vault | Daily reading / graph in Obsidian |
| **B — GitHub** | `vault/Thinking/` on `main` | Cloud backup + Quartz |

They are independent mirrors of Notion. Local direct sync does **not** replace GitHub backup.

## One-time Mac setup

### 1. Confirm vault path

Obsidian → **Manage vaults** → copy the path for **Thinking valut**.

Your current path (from Manage vaults):

```text
/Users/carrylewis/Library/Mobile Documents/iCloud~md~obsidian/Documents
```

Notes land in that folder under `Thinking/`.

### 2. Pull latest code

```bash
cd ~/Documents/research_brief
git pull
```

### 3. Put Notion secrets in `.env` (gitignored — never commit)

```bash
cat > ~/Documents/research_brief/.env <<'EOF'
NOTION_TOKEN=REPLACE_WITH_YOUR_TOKEN
NOTION_THINKING_DATABASE_ID=51e7fdfd-46f8-4d85-a813-f68b56131615
EOF
```

### 4. Run direct sync once

```bash
export OBSIDIAN_VAULT="/Users/carrylewis/Library/Mobile Documents/iCloud~md~obsidian/Documents"
chmod +x ~/Documents/research_brief/scripts/sync-to-local-obsidian.sh
~/Documents/research_brief/scripts/sync-to-local-obsidian.sh
tail -50 ~/Library/Logs/thinking-vault-sync.log
```

Open Obsidian → `Thinking/`.

### 5. Auto schedule (pick one)

- **每天 06:00（推荐）**：见 [`MAC_SHORTCUTS_DAILY_SYNC.md`](./MAC_SHORTCUTS_DAILY_SYNC.md)  
  （Apple 快捷指令，或 `com.carrylewis.thinking-vault-sync-daily` LaunchAgent）
- **每 15 分钟（旧）**：`scripts/macos/com.carrylewis.thinking-vault-sync.plist.example` — 一般不再需要

## Notes

- Sync **overwrites** Notion-linked notes under `Thinking/` by `source_id`.
- SQLite index: `~/Documents/research_brief/data/` (kept off iCloud).
- Do not `git init` inside the iCloud Obsidian folder.
- SSL errors like `UNEXPECTED_EOF_WHILE_READING` usually mean the network path to Notion is broken.
  **Fix:** open Clash/Surge (port 7890) *or* ensure direct HTTPS works; the sync script auto-uses 7890 when that port is listening.
- Rotate the Notion integration secret if it was pasted into chat.
