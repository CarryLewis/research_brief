# Thinking Vault

Notion Thinking Database → Obsidian `vault/Thinking/` one-way sync. Runtime is **GitHub Actions**, not a local API.

```text
Notion property columns + page body
        ↓
GitHub Actions (every 6 hours, or Run workflow)
        ↓
vault/Thinking/*.md   +   state/thinking_sync.db
        ↓
git commit / push
        ↓
Local Obsidian: git pull, open vault/
```

## Setup (once)

1. Create the Notion database using [`docs/architecture/NOTION_THINKING_DATABASE_CHECKLIST.md`](docs/architecture/NOTION_THINKING_DATABASE_CHECKLIST.md).
2. In the repo: **Settings → Secrets and variables → Actions**, add:
   - `NOTION_TOKEN` — Notion Internal Integration secret
   - `NOTION_THINKING_DATABASE_ID` — database id from the Notion URL
3. Actions → **Thinking Vault Sync** → **Run workflow** (or wait for the 6-hour schedule).

Workflow: [`.github/workflows/thinking-sync.yml`](.github/workflows/thinking-sync.yml)

## Vault layout

```text
vault/
  .obsidian/             # open this folder as an Obsidian vault
  Thinking/              # synced notes (identity = frontmatter source_id)
  Archive/Thinking/      # soft-archive when a Notion page disappears
state/
  thinking_sync.db       # sync index (committed so Actions remember renames)
```

On your machine: `git pull`, then Open folder as vault → `vault/`.

## Local debug (optional)

The CLI is only for debugging. Daily use is Actions.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # fill NOTION_TOKEN + NOTION_THINKING_DATABASE_ID
python -m app.cli.thinking_sync --vault ../vault
python -m app.cli.thinking_sync --status
```

Tests: `cd backend && pytest -q`

## Architecture

Canonical contract: [`docs/architecture/THINKING_VAULT_ARCHITECTURE.md`](docs/architecture/THINKING_VAULT_ARCHITECTURE.md)
