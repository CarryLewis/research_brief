# Environment & planning status (2026-08-20 audit)

**Status:** Snapshot of what is configured, what shipped, and where design docs still disagree.  
**Not a new product SoT.** Architecture and product rules remain in the documents listed below.

Companion: [`AGENTS.md`](../../AGENTS.md) · Cloud bootstrap: [`.cursor/environment.json`](../../.cursor/environment.json)

---

## 1. Environments (as actually used)

This repo is **not** a single runtime. Four environments coexist:

| Environment | What it is | Status on 2026-08-20 |
|-------------|------------|----------------------|
| **Cursor Cloud Agent** | Isolated Ubuntu VM for coding agents | **No linked dashboard environment.** This audit adds repo-managed `.cursor/environment.json` (Python venv + Quartz `npm ci`). Create / save the environment on the [Cloud Agents dashboard](https://cursor.com/dashboard/cloud-agents) so future agents boot from it. |
| **GitHub Actions** | Hourly Notion → `vault/Thinking/` | **Live.** [`.github/workflows/thinking-sync.yml`](../../.github/workflows/thinking-sync.yml) needs secrets `NOTION_TOKEN` + `NOTION_THINKING_DATABASE_ID`. Commits with `[skip ci]`. **No pytest CI on `main`.** |
| **Local Mac → iCloud Obsidian** | Direct Notion API write into the Obsidian vault | **Documented and scripted.** [`LOCAL_NOTION_OBSIDIAN_SYNC.md`](LOCAL_NOTION_OBSIDIAN_SYNC.md) + [`scripts/sync-to-local-obsidian.sh`](../../scripts/sync-to-local-obsidian.sh). Independent of GitHub; GitHub remains backup + Quartz source. |
| **Cloudflare Pages (Quartz)** | Public garden from `vault/` | **Code in `site/`.** Deploy guide: [`QUARTZ_CLOUDFLARE_DEPLOY.md`](QUARTZ_CLOUDFLARE_DEPLOY.md). `baseUrl` still defaults to `example.com`. |

### 1.1 Cursor Cloud gap (why agents start “empty”)

`environment-info` for a typical run currently returns `environment: null` and `build: null`. Resolution order is:

1. `.cursor/environment.json` in the git revision
2. Personal saved environment
3. Team saved environment

Until (1) lands on the default branch **and** an environment is saved in the dashboard, Cloud Agents JIT-clone the repo without a prepared venv / `node_modules`.

`install` in `.cursor/environment.json` is idempotent and terminating (venv + pip + optional `npm ci`). It does **not** start uvicorn or Quartz. Live Notion / LLM keys belong in Cursor **Secrets**, never in this file.

### 1.2 Local path / rename drift

GitHub repo is now [`CarryLewis/notion-obsidian-connect`](https://github.com/CarryLewis/notion-obsidian-connect). Several operator docs and scripts still assume the old clone path and name `research_brief`:

- `~/Documents/research_brief` in Mac sync docs and [`scripts/sync-to-local-obsidian.sh`](../../scripts/sync-to-local-obsidian.sh)
- Clone URL `github.com/CarryLewis/research_brief` in the Notion checklist and Quartz footer
- Workflow SQLite cache file still named `data/research_brief.db` (harmless as a cache key)

If the Mac clone still lives at `~/Documents/research_brief`, those defaults still work. New clones should set `RESEARCH_BRIEF_REPO` (or we rename that env var later). Do not change the default path without confirming the user’s machine.

---

## 2. Planning stack (who wins)

Locked hierarchy from [`THINKING_VAULT_MIGRATION.md`](THINKING_VAULT_MIGRATION.md):

| Rank | Document | Role |
|------|----------|------|
| 1 | [`THINKING_VAULT_ARCHITECTURE.md`](THINKING_VAULT_ARCHITECTURE.md) | Canonical for Thinking + sync + `Information/` · `Thinking/` · `Research/` |
| 2 | [`THINKING_VAULT_MIGRATION.md`](THINKING_VAULT_MIGRATION.md) | Conflict table + original phase order |
| 3 | [`ARCHITECTURE.md`](../ARCHITECTURE.md) | Knowledge OS inventory (Lake / KO / Lifecycle / Graph) |
| 4 | [`PRODUCT_v1.md`](../PRODUCT_v1.md) | Matter-style **Library / Information** capture only |
| 5 | [`TECH_FEASIBILITY_v1.md`](../TECH_FEASIBILITY_v1.md) | Feasibility notes for that Library path |

Obsidian-facing folders/graph: [`OBSIDIAN_CONSTITUTION_V1_1.md`](OBSIDIAN_CONSTITUTION_V1_1.md) (conflicts: [`OBSIDIAN_CONSTITUTION_CONFLICTS.md`](OBSIDIAN_CONSTITUTION_CONFLICTS.md)).

Three product stories still sit in the same git tree:

```text
A. Thinking Vault   Notion AI → Thinking DB → vault/Thinking/*.md → (later) Research
B. Library v1       Browser / email / URL → Information/*.md → Quartz / Website
C. Knowledge OS     Connectors → Lake + SQLite KO → Lifecycle / Graph Engine
```

**Daily priority on `main`:** A is production (Actions + CLI). B exists as code (`extension/` + `library_writer` → `Information/`). C exists as backend inventory and is **not** the daily UX.

---

## 3. Shipped vs planned

### 3.1 Thinking Vault (priority)

Original phases in the migration doc:

| Phase | Intent | On `main` |
|-------|--------|-----------|
| 1 Audit | Reuse map | Done |
| 2 Docs + canonical model | `ThinkingObject` + tests | **Done** |
| 3 Notion adapter | Read DB + body + relations | **Done** (`thinking_vault/`) |
| 4 Writer | `Thinking/*.md`, `source_id`, rename | **Done** |
| 5 Sync engine | Idempotent CLI + API + soft-archive | **Done** + **GitHub Actions hourly** |
| 6 Graph | Wikilinks survive; optional `maybe_auto_sync` | **Partial.** Relations become `[[wikilinks]]`. Thinking sync does **not** call Graph Engine. Graph still keys off Knowledge OS notebooks. |
| 7 Website | Consume Obsidian-derived Thinking; no second Thinking DB | **Partial.** Quartz reads `vault/` (excludes `Archive/`, `90_Meta/`). Not a Thinking database. Domain still `example.com`. |

Extra behavior landed after the original V1 spec:

- `Status=folder` → real directories + `.thinking-folder` sidecars
- Notion **Tags** → page-bottom `#tags`
- Page body → `## Extended Reflection` (architecture locked this; see §4)

Vault today: `Thinking/` has many synced notes; `Information/` is almost empty (one note + `Attachments/`); `Research/` is empty. That matches “Thinking first, Research later.”

### 3.2 Library / Information (PRODUCT_v1)

[`TECH_FEASIBILITY_v1.md`](../TECH_FEASIBILITY_v1.md) §3 still says there is no extension and no website. **That is outdated.**

| Milestone (feasibility §9) | Code |
|----------------------------|------|
| M1 Readable parse + writer + `POST /api/library/save` | **Done** — writes **`Information/`** (not `Library/Articles/`) |
| M2 Chrome MV3 extension | **Done** (`extension/`) — README / manifest still say “Library” |
| M3 Email inbound → vault note | Pipeline exists; not the daily path |
| M4 Open Library books | Not a productized daily path |
| M5 Website mirror by `visibility=public` | Quartz publishes the garden; **no** `visibility` filter yet |
| M6 Selection highlights | Not built |

Health endpoint still reports `mode: library-v1` and `service: research-brief`.

### 3.3 Knowledge OS (`ARCHITECTURE.md`)

Lake, KO, Lifecycle, Graph Engine, and CLIs are still in `backend/`. Constitution V1 folder forest is **not** the daily vault (files live under `Archive/`). Do not implement new UX against `ARCHITECTURE.md` §6.

---

## 4. Design contradictions still in the docs

These are documentation bugs, not new product decisions:

| Topic | Conflict | Treat as |
|-------|----------|----------|
| Notion page body | Checklist header: “page body is not synced in V1.” Architecture: property columns **and** page body (`## Extended Reflection`). | **Architecture wins** — body is synced. |
| Tags vs “no taxonomy” | Constitution: tags must not become a second taxonomy. Checklist + `workspace.yaml`: controlled Tags multi-select → footer `#tag`. | Shipped behavior is Tags-as-filters. Keep them off the graph. |
| `Status=folder` vs Type | Architecture uses `Status=folder`. Open PR #8 wants independent **Type** (`thinking` / `folder`) and Status as maturity only. | `main` = Status=folder. Type split is an unmerged proposal. |
| Capture into vault | Old Constitution: capture never mirrors. PRODUCT + V1.1: capture **must** write `Information/`. | V1.1 / PRODUCT for Information; Lake remains byte SoT. |
| Extension copy | Writer → `Information/`. Extension README still says `Library/Articles/` + `Library/Attachments/`. | Code path is `Information/`. |
| Repo name | README / GitHub: `notion-obsidian-connect`. Quartz layout, deploy guide, Mac scripts: `research_brief`. | GitHub name is current; local path may still be old. |

[`THINKING_VAULT_ARCHITECTURE.md`](THINKING_VAULT_ARCHITECTURE.md) §1.4 “Missing (must build)” is a historical gap list. Those modules exist on `main`.

---

## 5. Open PRs that would change the plan

Do not treat these as `main` until merged:

| PR | Intent | Why it matters |
|----|--------|----------------|
| [#8](https://github.com/CarryLewis/notion-obsidian-connect/pull/8) **Slim repo to Thinking Vault** (OPEN) | Delete FastAPI, Library, extension, Quartz, Knowledge OS; keep Actions + `thinking_vault` | Directly contradicts keeping B + C in-tree. Product fork: “sync-only repo” vs “observatory monorepo.” |
| [#11](https://github.com/CarryLewis/notion-obsidian-connect/pull/11) MUJI homepage prototype (DRAFT) | Static `frontend/` editorial homepage + design constitution | New public surface, separate from Quartz garden. |
| [#10](https://github.com/CarryLewis/notion-obsidian-connect/pull/10) Thinking Vault talk slides (DRAFT) | HTML slides | Docs/comms only. |

Until #8 is accepted or closed, Cloud install still bootstraps **the full `main` tree** (backend + Quartz), not the slimmed fork.

---

## 6. Recommended next decisions (planning, not estimates)

1. **Save a Cursor Cloud environment** that uses this repo’s `.cursor/environment.json`, then enable Builds from the environment page so agents skip JIT pip/npm.
2. **Decide the product fork:** keep the observatory monorepo (`main`), or merge #8 and make GitHub a Thinking-only mirror. That single choice retires most doc dual-SoT pain.
3. **If staying on `main`:** fix operator copy (extension README, API docstring, Quartz GitHub URL, checklist “page body” line) and add a pytest workflow. Leave Mac `~/Documents/research_brief` defaults until the machine path is confirmed.
4. **Do not** start Phase 6 Graph-as-product or auto Research Briefs. Quartz can stay a read-only garden; optional next publish step is `visibility=public` filtering, not a second Thinking DB.
5. **Secrets:** Notion tokens stay in GitHub Actions secrets and (optionally) Cursor environment secrets. Never commit them.

---

*Update this file when a phase lands or a SoT document changes. Do not let it become a third constitution.*
