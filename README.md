# Research Brief Studio — Personal Observatory

**Obsidian-facing architecture:** [`docs/architecture/OBSIDIAN_CONSTITUTION_V1_1.md`](docs/architecture/OBSIDIAN_CONSTITUTION_V1_1.md)  
**Conflict reconciliation:** [`docs/architecture/OBSIDIAN_CONSTITUTION_CONFLICTS.md`](docs/architecture/OBSIDIAN_CONSTITUTION_CONFLICTS.md)  
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

AI proposes relationships; humans accept meaningful links. No Inbox dump. No domain folder taxonomy.

## Quick start

```bash
cd backend && source .venv/bin/activate

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
python -m app.cli.graph view --view default --notebook nb_xxx --fresh
python -m app.cli.graph suggest-links --notebook nb_xxx

# API
uvicorn app.main:app --app-dir backend --reload --port 8000
```

### Vault layout (Constitution V1.1)

```text
Information/                 # external world — readable captures
Thinking/                    # personal reflections, questions, fragments
Research/                    # mature syntheses / Research Briefs
Archive/                     # cold legacy only
90_Meta/                     # system conventions (not cognitive nodes)
```

## Config

| File | Role |
|------|------|
| [`backend/configs/workspace.yaml`](backend/configs/workspace.yaml) | Cognitive vault folders, sync limits |
| [`backend/configs/lifecycle.yaml`](backend/configs/lifecycle.yaml) | Stages, scoring, signal connectors, AI flags |
| [`backend/configs/graph.yaml`](backend/configs/graph.yaml) | Graph views, weight formula, anti-pollution |
| [`backend/configs/channels.yaml`](backend/configs/channels.yaml) | Connectors |
| [`.env.example`](.env.example) | `DEFAULT_VAULT_PATH`, `CONTENT_LAKE_DIR`, LLM, inbound, digest |

## Evolution of this architecture

| Milestone | Idea |
|-----------|------|
| Thinking Workspace | Raw out of Obsidian; Content Lake + KO spine |
| Constitution V1 | Typed Concepts/Projects/…; Resources stay in DB — **superseded for vault UX** |
| PRODUCT_v1 Library | Capture writes readable notes — **path remapped to Information/** |
| Lifecycle + Graph Engine | Backend evolution + propose-only cognitive graph |
| **Constitution V1.1** | Minimal vault: Information / Thinking / Research; quality over density |

Details: **[docs/architecture/OBSIDIAN_CONSTITUTION_V1_1.md](docs/architecture/OBSIDIAN_CONSTITUTION_V1_1.md)**.
