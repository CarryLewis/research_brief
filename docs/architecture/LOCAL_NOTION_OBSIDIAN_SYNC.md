# Local Notion → Obsidian (iCloud Thinking valut)

**Goal:** Notion Thinking database writes **directly** into your Mac Obsidian vault (iCloud) for daily use, **while GitHub keeps a full repo backup**.

## Dual pipeline (both kept)

```text
                         ┌─ (A) Mac LaunchAgent / script ──► iCloud Obsidian “Thinking valut”
Notion Thinking DB ──────┤
                         └─ (B) GitHub Actions (hourly) ───► GitHub repo vault/  (backup + Quartz)
```

| Path | Destination | Purpose |
|------|-------------|---------|
| **A — local** | iCloud Obsidian vault | What you open and edit in Obsidian |
| **B — GitHub** | `CarryLewis/research_brief` → `vault/Thinking/` | Cloud backup + site build source |

They are **independent mirrors of Notion**, not copies of each other. Turning on local direct sync does **not** disable GitHub backup.

### Keep GitHub backup healthy

1. Repo secrets (Settings → Secrets → Actions): `NOTION_TOKEN`, `NOTION_THINKING_DATABASE_ID`
2. Workflow: [`.github/workflows/thinking-sync.yml`](../../.github/workflows/thinking-sync.yml) — cron hourly + manual **Run workflow**
3. After a run, check `vault/Thinking/` on `main` for new commits like `chore(thinking): sync Notion Thinking Vault`

Local Obsidian path (A):

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
