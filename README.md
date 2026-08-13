# Research Brief Studio — Personal Observatory

**Thinking Vault (priority):** [`docs/architecture/THINKING_VAULT_ARCHITECTURE.md`](docs/architecture/THINKING_VAULT_ARCHITECTURE.md) — Notion property columns → `Thinking/*.md` one-way sync.

**Obsidian-facing architecture:** [`docs/architecture/OBSIDIAN_CONSTITUTION_V1_1.md`](docs/architecture/OBSIDIAN_CONSTITUTION_V1_1.md)  
**System architecture (Lake / KO / Lifecycle / Graph Engine):** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)  
**Product Capture · Annotate · Publish:** [`docs/PRODUCT_v1.md`](docs/PRODUCT_v1.md)

Layers:

1. **Content Lake** — immutable originals (`DATA_DIR/content_lake`) — backend only
2. **Knowledge Database** — SQLite Knowledge Objects, edges, proposals
3. **Graph Engine** — cognitive projection (JSON API; propose links; no infrastructure nodes)
4. **Cognitive Vault (Obsidian)** — `Information/` · `Thinking/` · `Research/`

```text
Observe → Capture → Information
Experience → Conversation → Thinking
Connections accumulate → Research Brief (synthesis)
```

## Thinking Vault on GitHub (scheduled sync)

Primary runtime for Notion → vault sync is **GitHub Actions** (hourly + manual).

1. Repo Settings → Secrets and variables → Actions → add:
   - `NOTION_TOKEN`
   - `NOTION_THINKING_DATABASE_ID`
2. Workflow: [`.github/workflows/thinking-sync.yml`](.github/workflows/thinking-sync.yml)
3. Writes into the repo’s [`vault/`](vault/) and commits when notes change.
4. Actions → **Thinking Vault Sync** → Run workflow (optional manual trigger).

SQLite sync index is cached across runs; if the cache is cold, sync hydrates identity from on-disk `source_id` / `.thinking-folder` sidecars.

Local CLI remains available for debugging.

## Public website (Quartz + Cloudflare)

Publish the Obsidian-style garden from `vault/` with Quartz:

- Code: [`site/`](site/)
- Guide: [`docs/architecture/QUARTZ_CLOUDFLARE_DEPLOY.md`](docs/architecture/QUARTZ_CLOUDFLARE_DEPLOY.md)
- Connect the repo to **Cloudflare Pages** (root directory `site`, build `npm ci && npm run build`, output `public`), then bind your existing domain.

AI proposes relationships; humans accept meaningful links. No Inbox dump. No domain folder taxonomy.

## Quick start

```bash
cd backend && source .venv/bin/activate

# Thinking Vault: Notion → vault/Thinking/ (local debug)
# (requires NOTION_TOKEN + NOTION_THINKING_DATABASE_ID; see docs/architecture/NOTION_THINKING_DATABASE_CHECKLIST.md)
python -m app.cli.thinking_sync --vault ../vault
python -m app.cli.thinking_sync --status

# Capture → Lake + KO; Library/save writes Information/ notes
python -m app.cli.collect --job ../jobs/nature_migraine.yaml --no-media

# Lifecycle (backend; not daily vault bureaucracy)
python -m app.cli.lifecycle backfill
python -m app.cli.lifecycle evaluate --notebook nb_xxx
python -m app.cli.lifecycle proposals

# Workspace sync → Thinking / Research cognitive folders
python -m app.cli.workspace sync --notebook nb_xxx --vault ../vault

# Cognitive graph (portable JSON — propose-only AI links)
python -m app.cli.graph sync --notebook nb_xxx
python -m app.cli.graph view --view research --notebook nb_xxx --fresh
python -m app.cli.graph neighborhood --ko ko_xxx --depth 2
python -m app.cli.graph metrics --notebook nb_xxx
python -m app.cli.graph suggest-links --notebook nb_xxx

# API
uvicorn app.main:app --app-dir backend --reload --port 8000
```

### Vault layout (Constitution V1.1)

```text
Information/            # world memory (readable captures)
Thinking/               # Notion-synced + personal fragments
Research/               # synthesis / briefs
Archive/                # cold legacy + Digests
90_Meta/
```

## Config

| File | Role |
|------|------|
| [`backend/configs/workspace.yaml`](backend/configs/workspace.yaml) | Cognitive folders, roles, Thinking Vault property map |
| [`backend/configs/lifecycle.yaml`](backend/configs/lifecycle.yaml) | Stages, scoring, signal connectors, AI flags |
| [`backend/configs/graph.yaml`](backend/configs/graph.yaml) | Graph views, weight formula, auto-sync |
| [`backend/configs/channels.yaml`](backend/configs/channels.yaml) | Connectors |
| [`.env.example`](.env.example) | `DEFAULT_VAULT_PATH`, Notion tokens, LLM, inbound, digest |

Details: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** · **[docs/architecture/THINKING_VAULT_ARCHITECTURE.md](docs/architecture/THINKING_VAULT_ARCHITECTURE.md)**.
