# Research Brief Studio — Knowledge OS

**Thinking Vault (priority):** [`docs/architecture/THINKING_VAULT_ARCHITECTURE.md`](docs/architecture/THINKING_VAULT_ARCHITECTURE.md) — Notion property columns → `Thinking/*.md` one-way sync.

Canonical Knowledge OS inventory: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**

Four layers + intellectual lifecycle:

1. **Content Lake** — immutable originals (`DATA_DIR/content_lake`)
2. **Knowledge Database** — SQLite Knowledge Objects, edges, maturity, history
3. **Graph Engine** — cognitive projection (JSON API; not Obsidian Graph)
4. **Research Workspace** — Obsidian thinking surface (curated note types only)

Capture never mirrors articles/papers into Obsidian. Promote deliberately. AI proposes; humans confirm maturity and Insights.

```text
Signal → Resource → Knowledge Object → Reflection → Concept → Project → Insight
                                              ↘ Question ↗
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

## Quick start

```bash
cd backend && source .venv/bin/activate

# Thinking Vault: Notion → vault/Thinking/ (local debug)
# (requires NOTION_TOKEN + NOTION_THINKING_DATABASE_ID; see docs/architecture/NOTION_THINKING_DATABASE_CHECKLIST.md)
python -m app.cli.thinking_sync --vault ../vault
python -m app.cli.thinking_sync --status

# Capture → Lake + Resource/Signal KO (vault unchanged)
python -m app.cli.collect --job ../jobs/nature_migraine.yaml --no-media

# Lifecycle
python -m app.cli.lifecycle backfill
python -m app.cli.lifecycle evaluate --notebook nb_xxx
python -m app.cli.lifecycle proposals
python -m app.cli.lifecycle accept --proposal lpr_xxx --vault ../vault
python -m app.cli.lifecycle evolution --ko ko_xxx
python -m app.cli.lifecycle central
python -m app.cli.lifecycle filter-signal --ko ko_xxx
python -m app.cli.lifecycle assist-reflection --id ko_xxx
python -m app.cli.lifecycle project-context --id ko_xxx
python -m app.cli.lifecycle draft-insight --notebook nb_xxx --support ko_a,ko_b

# Workspace curation
python -m app.cli.workspace suggestions
python -m app.cli.workspace promote --id ko_xxx --role concept --vault ../vault
python -m app.cli.workspace sync --notebook nb_xxx --vault ../vault

# Digests → Reports/ (graph: false)
python -m app.cli.digest --period daily --dry-run

# Cognitive graph (portable JSON — no visualization)
python -m app.cli.graph sync --notebook nb_xxx
python -m app.cli.graph view --view research --notebook nb_xxx --fresh
python -m app.cli.graph neighborhood --ko ko_xxx --depth 2
python -m app.cli.graph metrics --notebook nb_xxx
python -m app.cli.graph suggest-links --notebook nb_xxx

# API
uvicorn app.main:app --app-dir backend --reload --port 8000
```

### Vault layout

```text
Reflections/                 # freeform thinking (daily home)
Projects/  Concepts/  Books/
Insights/                    # optional
Reports/Daily|Weekly/…
Collections/                 # human only
Archive/Legacy|PreConstitution-Inbox/
90_Meta/
```

## Config

| File | Role |
|------|------|
| [`backend/configs/workspace.yaml`](backend/configs/workspace.yaml) | Obsidian folders, tags, suggestion threshold |
| [`backend/configs/lifecycle.yaml`](backend/configs/lifecycle.yaml) | Stages, scoring, signal connectors, AI flags |
| [`backend/configs/graph.yaml`](backend/configs/graph.yaml) | Graph views, weight formula, auto-sync |
| [`backend/configs/channels.yaml`](backend/configs/channels.yaml) | Connectors |
| [`.env.example`](.env.example) | `DEFAULT_VAULT_PATH`, `CONTENT_LAKE_DIR`, LLM, inbound, digest |

## Evolution of this architecture

| Milestone | Idea |
|-----------|------|
| Thinking Workspace | Raw out of Obsidian; Content Lake + KO spine |
| Constitution V1 | Only Concept/Project/Reflection/Book/Report sync; Resources stay in DB |
| Lifecycle Engine | Stages, maturity scores, append-only history, Reflection/Question/Insight |
| Lifecycle AI | Signal filter, question assist, project context pack, insight drafts |
| Graph Engine V1 | Cognitive projection, named views, metrics, communities, graph API |

Details, entity schemas, APIs, migration, and non-goals: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.
