# Thinking Vault V1 — Migration & Conflict Resolution

**Status:** Binding conflict table under Thinking Vault priority (2026-08)  
**Companion:** [`THINKING_VAULT_ARCHITECTURE.md`](THINKING_VAULT_ARCHITECTURE.md)

Every conflicting rule below is classified as **KEEP**, **MODIFY**, **DEPRECATE**, or **REMOVE**.  
Silent coexistence of obsolete rules is not allowed after implementation lands.

---

## 1. Source-of-truth hierarchy (new)

| Rank | Document | Role after this decision |
|------|----------|--------------------------|
| 1 | `docs/architecture/THINKING_VAULT_ARCHITECTURE.md` | **Canonical** for Thinking + sync + vault cognitive roots |
| 2 | This migration doc | Conflict resolutions and phase order |
| 3 | `docs/ARCHITECTURE.md` | Historical Knowledge OS inventory; must be banner-updated |
| 4 | `docs/PRODUCT_v1.md` | Remains SoT for **Library reading capture** only; demoted where it conflicts with Thinking Vault |
| 5 | `docs/TECH_FEASIBILITY_v1.md` | Feasibility notes; update pointers when implementing |

---

## 2. Locked migration choices

| Topic | Decision |
|-------|----------|
| Priority | Thinking Vault wins conflicts |
| Vault roots | Move toward `Information/` · `Thinking/` · `Research/` |
| Thinking SoT | Notion **property columns + page body** → Obsidian (one-way overwrite by `source_id`) |
| Page body | Synced as `## Extended Reflection` (detailed reflection); properties remain structured slots |
| SQLite | Sync index + optional graph projection — not competing editor |
| Constitution `Reflections/` | Transitional; new Notion-sourced objects write to `Thinking/` |
| Library `Library/` | KEEP for Information reading path until Information migration |
| Bidirectional vault↔DB reflection preserve | **MODIFY** for Notion-sourced Thinking: overwrite allowed |

---

## 3. Conflict classification

### 3.1 Product / documentation rules

| Rule (current) | Location | Class | Action |
|----------------|----------|-------|--------|
| Notion / website UI as non-goals | `ARCHITECTURE.md` §13 | **REMOVE** | Notion is Thinking input; website remains later consumer |
| Obsidian is Thinking Workspace; Resources never dump | `ARCHITECTURE.md` §1, Constitution | **KEEP** for Information capture → Lake/KO | Align wording: Obsidian = cognitive memory for Thinking + curated Information presentation |
| PRODUCT_v1 is sole product SoT; ARCHITECTURE is historical only | `PRODUCT_v1.md` header | **MODIFY** | Split SoT: Library capture vs Thinking Vault |
| Obsidian = private reading library only | `PRODUCT_v1.md` §2–3 | **MODIFY** | Reading library remains for Information; Thinking uses `Thinking/` |
| Capture must write readable Library notes | `PRODUCT_v1.md`, `TECH_FEASIBILITY_v1` | **KEEP** | Information path only; do not apply to Thinking |
| Constitution “do not replace folder purpose rules” | `ARCHITECTURE.md` §13 | **MODIFY** | Folder purpose evolves to Information/Thinking/Research |
| Welcome guides Library-only reading | PRODUCT + `vault/Welcome.md` | **MODIFY** | Dual guidance: read Information; think via Notion → `Thinking/` |
| Dual SoT without banner | docs | **REMOVE** | Add explicit banners pointing here |

### 3.2 Vault folder rules

| Rule | Class | Action |
|------|-------|--------|
| Roots: Concepts/Projects/Reflections/Books/Reports/… | **DEPRECATE** as primary IA | Keep files in place; stop promoting as day-to-day home |
| Roots: Library/Articles\|Emails\|Books | **KEEP** (transitional Information) | Later map/rename toward `Information/` if needed |
| Target roots: Information/Thinking/Research | **MODIFY** (introduce) | Scaffold in workspace config; Writer targets `Thinking/` |
| Thinking/Ideas\|Clinical\|Questions subfolders | **REMOVE** (never add) | Flat `Thinking/*.md` only |
| Archive/ for history | **KEEP** | Soft-delete / Notion deletion lands here |
| 90_Meta conventions | **KEEP** | Update Import Conventions for Thinking sync |
| Collections/ human indexes | **KEEP** | Unchanged |

### 3.3 Authority & sync rules

| Rule | Class | Action |
|------|-------|--------|
| SQLite Reflection is SoT; vault is projection | **MODIFY** | For Notion Thinking: Notion/Obsidian file is content SoT; SQLite is index |
| `preserve_existing_reflection_files` skips overwrite | **MODIFY** | Does **not** apply to Notion-synced `Thinking/` files |
| API reflection force-write to Reflections/ | **KEEP** temporarily | Manual/API reflections may still use old path until cutover |
| Bidirectional Obsidian ↔ DB sync | **KEEP** as non-goal | Still out of scope |
| One-way Notion → Obsidian | **MODIFY** (new requirement) | Implement sync engine |
| Filename as identity | **REMOVE** for Thinking sync | Use `source_id` only |
| Natural human-readable filenames | **KEEP** | Reuse `_natural_stem` patterns |
| Hard-delete on remote delete | **REMOVE** | Soft-archive instead |

### 3.4 Data model / ontology

| Rule | Class | Action |
|------|-------|--------|
| KO universal spine | **KEEP** | Optional projection for graph; not required for Markdown write |
| Reflection / Question / Insight tables | **KEEP** | May mirror Notion Thinking later; do not block V1 Markdown path |
| Heavy lifecycle maturity as UX | **DEPRECATE** for Thinking capture UX | Backend may retain scores; user sees natural language |
| workspace_role gate for vault notes | **MODIFY** | Add path for `thinking` (or map Notion sync outside promote gate) |
| Large Notion property taxonomies | **REMOVE** | Minimal DB properties only |
| Page body headings as Thinking content SoT | **MODIFY** | Structured SoT = property columns; narrative SoT = page body → `page_body` |
| Parse page body `##` sections for sync | **REMOVE** for structured slots | Structured fields still come from properties only |
| Sync Notion page blocks | **MODIFY** (add) | Convert blocks → Markdown under `## Extended Reflection` |
| Graph Engine rebuild / views | **KEEP** | Wire after Thinking files exist; no auto-link spam |
| AI auto-create Concept vault notes | **KEEP** (still forbidden) | Propose only |
| Suggest questions on reflection | **KEEP** optional | Must not overwrite Raw Thought |

### 3.5 Pipelines & APIs

| Rule | Class | Action |
|------|-------|--------|
| Collect / ingest / Lake for world info | **KEEP** | Separate from Thinking |
| Library `/api/library/save` | **KEEP** | Information only |
| Inbound email webhook | **KEEP** | Not Notion |
| Workspace sync CLI/API | **KEEP** | Constitution notes; parallel to Thinking sync |
| New Thinking sync CLI/API | **MODIFY** (add) | `sync-thinking` + `POST /api/thinking/sync` |
| Merge Notion into collect or library_writer | **REMOVE** | Forbidden |
| Website independent Thinking DB | **REMOVE** | Forbidden in V1 |
| Research Brief auto-generation | **DEPRECATE** / defer | Out of V1 |

### 3.6 Frontmatter & note shape

| Rule | Class | Action |
|------|-------|--------|
| Reflection freeform minimal frontmatter (`title/type/date/graph`) | **MODIFY** for Notion Thinking | Use `source/source_id/created/updated`; omit heavy schema |
| Library note frontmatter (visibility, authors, …) | **KEEP** | Information notes only |
| Six-section Concept skeleton | **KEEP** for legacy Concept notes | Not used for Thinking Objects |
| Thinking sections (Raw Thought, …) | **MODIFY** (add) | Omit empty sections |
| Preserve Raw Thought always | **MODIFY** (new hard rule) | Tests must lock this |

---

## 4. Code impact summary

### 4.1 Files to create

| Path | Purpose |
|------|---------|
| `docs/architecture/THINKING_VAULT_ARCHITECTURE.md` | Done (architecture SoT) |
| `docs/architecture/THINKING_VAULT_MIGRATION.md` | Done (this file) |
| `backend/app/services/thinking_vault/` | model, adapter, normalizer, writer, sync |
| `backend/app/connectors/notion.py` (or client module) | Notion read API |
| `backend/app/cli/thinking_sync.py` | Manual / scheduled sync |
| `backend/tests/test_thinking_vault_*.py` | Model / writer / sync / idempotency |
| Vault `Thinking/` + Archive policy notes | Scaffold |

### 4.2 Files to change (minimal)

| Path | Change |
|------|--------|
| `docs/ARCHITECTURE.md` | Banner: Thinking Vault supersedes Notion non-goal + folder IA |
| `docs/PRODUCT_v1.md` | Banner: SoT limited to Library Information path |
| `backend/app/config.py` / `.env.example` | Notion token + database id |
| `backend/configs/workspace.yaml` | Add `thinking: Thinking`, `information`, `research` folder keys |
| `backend/app/api.py` | `POST /api/thinking/sync` (+ status) |
| `backend/app/db.py` | Sync state table or additive columns (`source`, `source_id`, …) via existing `_migrate_sqlite_columns` |
| `backend/app/services/workspace.py` | Share filename/atomic helpers; do not overload reflection preserve for Notion path |
| `vault/90_Meta/Import Conventions.md` | Document Notion → Thinking sync |
| `vault/Welcome.md` | Thinking Vault priority messaging |
| `README.md` | Point to Thinking Vault docs |

### 4.3 Files not to rewrite

- `content_lake.py`, collect connectors, `library_writer.py`, `readable.py`
- Graph engine core (only call after sync)
- Lifecycle maturity engine (leave; do not surface in Notion UX)

### 4.4 Database changes

Prefer additive:

- Sync state: `source_id` (unique), `vault_path`, `content_hash` / `notion_last_edited`, `status` (`active`|`archived`), timestamps
- Optional on KO: `connector=notion`, `metadata_json.source_id` — avoid large schema churn

No Alembic; follow existing `create_all` + `_add_column_if_missing`.

### 4.5 API changes

| Endpoint | Behavior |
|----------|----------|
| `POST /api/thinking/sync` | Run incremental Notion → Obsidian sync; return counts/errors |
| `GET /api/thinking/sync/status` (optional V1) | Last run, failures |
| Existing `/api/reflections` | KEEP; do not replace Notion UX in V1 |

---

## 5. Phased delivery (implementation order)

### Phase 1 — Audit (complete)

Repository inspected. Reusable modules and gaps recorded in Architecture §1.

### Phase 2 — Docs + canonical model

- Land these two docs + SoT banners
- Implement `ThinkingObject` model + serialize/normalize/identity tests  
- **No Notion network yet**

### Phase 3 — Notion Adapter

- Read database pages, body, metadata, relations
- Mocked tests; real token optional behind env

### Phase 4 — Obsidian Writer

- Write/update/rename under `Thinking/`
- Minimal frontmatter; Raw Thought preserved; no empty sections
- Duplicate prevention by `source_id`

### Phase 5 — Sync Engine

- Adapter → Normalizer → Writer
- Idempotent, incremental, logged, soft-archive deletes
- CLI + API trigger

### Phase 6 — Graph integration

- Ensure Wikilinks from relations survive
- Optional `graph_engine.maybe_auto_sync`
- No automatic semantic link creation

### Phase 7 — Website

- Only after Thinking → Obsidian is reliable
- Consume Obsidian-derived content; no second Thinking DB

---

## 6. Cutover notes for existing vault content

| Existing content | V1 handling |
|------------------|-------------|
| `Reflections/*.md` | KEEP in place; not auto-moved |
| `Concepts/` `Projects/` | KEEP; transitional graph nodes |
| `Library/` | KEEP as Information reading surface |
| New Notion Thinking | Write only to `Thinking/` |
| Future consolidation | Optional script to move Reflections → Thinking (not required for V1 sync) |

Do not mass-migrate or delete Constitution notes as part of enabling sync.

---

## 7. Acceptance gate before coding implementation Phases 3–5

1. Architecture + Migration docs reviewed  
2. SoT banners on `ARCHITECTURE.md` and `PRODUCT_v1.md`  
3. Canonical model tests green  
4. Notion integration credentials plan agreed (token + database id)

Then implement Adapter → Writer → Sync with minimum new surface area.
