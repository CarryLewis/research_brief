# Agent notes — notion-obsidian-connect

Personal Thinking Vault: **Notion → Obsidian** one-way sync, plus a Matter-style Information capture path and a Quartz public garden.

## Source-of-truth order

1. [`docs/architecture/THINKING_VAULT_ARCHITECTURE.md`](docs/architecture/THINKING_VAULT_ARCHITECTURE.md) — Thinking + Notion sync + vault cognitive roots
2. [`docs/architecture/OBSIDIAN_CONSTITUTION_V1_1.md`](docs/architecture/OBSIDIAN_CONSTITUTION_V1_1.md) — Obsidian-facing folders / graph rules
3. [`docs/PRODUCT_v1.md`](docs/PRODUCT_v1.md) — Library / Information capture · annotate · publish
4. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Knowledge OS inventory (Lake / KO / Lifecycle / Graph); not daily UX
5. Snapshot of shipped vs planned: [`docs/architecture/STATUS_AND_PLANNING.md`](docs/architecture/STATUS_AND_PLANNING.md)

When documents disagree, **Thinking Vault wins** for thinking/sync; **Constitution V1.1 wins** for vault layout.

## Layout

| Path | Role |
|------|------|
| `backend/` | FastAPI + Thinking Vault sync + Library save + Knowledge OS |
| `vault/` | Canonical Obsidian vault in git (`Information/` · `Thinking/` · `Research/`) |
| `extension/` | Chrome MV3 “Save to Library” → `POST /api/library/save` |
| `site/` | Quartz 4 garden (syncs from `vault/` at build time) |
| `jobs/` | Collect job YAML (Information / Lake path) |

Do not commit `.env`, `data/`, or Notion tokens.

## Commands

```bash
# Backend tests (no Notion secrets required)
cd backend && .venv/bin/pytest -q

# Thinking Vault local debug (needs NOTION_TOKEN + NOTION_THINKING_DATABASE_ID)
python -m app.cli.thinking_sync --vault ../vault
python -m app.cli.thinking_sync --status

# Local API (browser extension / library save)
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

# Quartz
cd site && npm run build
```

Scheduled production sync is GitHub Actions: [`.github/workflows/thinking-sync.yml`](.github/workflows/thinking-sync.yml). Secrets live in the GitHub repo, not in this file.

## Cursor Cloud specific instructions

`.cursor/environment.json` installs `python3-venv` if missing, then `backend/.venv` from `backend/requirements.txt`, then `site/node_modules` via `npm ci`.

- Unit tests do **not** need Notion or LLM secrets. Do not invent tokens in committed files.
- Live Notion sync in Cloud is optional. If `NOTION_TOKEN` / `NOTION_THINKING_DATABASE_ID` are missing, skip live sync and rely on mocked tests in `backend/tests/test_thinking_vault.py`.
- Do not start Quartz or uvicorn unless the task needs them. `install` must stay a terminating bootstrap.
- Prefer writing into `vault/Thinking/` only via the Thinking Vault writer (identity is Notion `source_id`). Do not mass-migrate `Archive/`.
- Open PRs that delete large subsystems (e.g. slimming away Library / Quartz / Knowledge OS) are product decisions — do not merge or continue that deletion unless the task explicitly asks.
