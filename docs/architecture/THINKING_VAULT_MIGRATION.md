# Thinking Vault V1 — Migration & Conflict Resolution

**Status:** Binding conflict table under Thinking Vault priority (2026-08)  
**Companion:** [`THINKING_VAULT_ARCHITECTURE.md`](THINKING_VAULT_ARCHITECTURE.md)

Every conflicting rule below is classified as **KEEP**, **MODIFY**, **DEPRECATE**, or **REMOVE**.

---

## 1. Source-of-truth hierarchy

| Rank | Document | Role |
|------|----------|------|
| 1 | `docs/architecture/THINKING_VAULT_ARCHITECTURE.md` | **Canonical** for Thinking + sync + vault cognitive roots |
| 2 | This migration doc | Conflict resolutions and phase order |
| 3 | `docs/architecture/NOTION_THINKING_DATABASE.md` | Human Notion DB setup checklist |
| 4 | `docs/ARCHITECTURE.md` | Historical Knowledge OS inventory |
| 5 | `docs/PRODUCT_v1.md` | SoT for **Library reading capture** only |

---

## 2. Locked migration choices

| Topic | Decision |
|-------|----------|
| Priority | Thinking Vault wins conflicts |
| Vault roots | `Information/` · `Thinking/` · `Research/` |
| Thinking content SoT | **Database property columns** → Obsidian (MODIFY from earlier “page body SoT”) |
| Sync | Notion → Obsidian one-way overwrite by `source_id` |
| SQLite | Sync index only |
| `Reflections/` | Transitional; new Notion objects → `Thinking/` |
| `Library/` | KEEP for Information until Information migration |
| Soft archive | `Archive/Thinking/` |

---

## 3. Conflict classification (summary)

| Rule | Class | Action |
|------|-------|--------|
| Notion as non-goal | **REMOVE** | Notion is Thinking input |
| PRODUCT_v1 sole product SoT | **MODIFY** | Split: Library vs Thinking Vault |
| Page body is Thinking content | **MODIFY** | V1: **properties** are content SoT; body is scratch |
| SQLite Reflection SoT | **MODIFY** | Notion/Obsidian file is Thinking SoT; SQLite indexes |
| `preserve_existing_reflection_files` | **MODIFY** | Does **not** apply to Notion `Thinking/` |
| Filename as identity | **REMOVE** | Use `source_id` |
| Hard-delete on remote delete | **REMOVE** | Soft-archive |
| Thinking taxonomy subfolders | **REMOVE** | Flat `Thinking/*.md` |
| Merge Notion into collect/library | **REMOVE** | Forbidden |
| Website Thinking DB | **REMOVE** | Forbidden in V1 |

Full historical tables remain valid under these overrides; implementers follow Architecture §3 for the property contract.

---

## 4. Code impact

### Create

| Path | Purpose |
|------|---------|
| `backend/app/services/thinking_vault/` | model, normalizer, markdown, later adapter/writer/sync |
| `backend/app/connectors/notion.py` | Notion read API (Phase 3) |
| `backend/app/cli/thinking_sync.py` | Sync trigger (Phase 5) |
| `backend/tests/test_thinking_vault_*.py` | Contract tests |
| Vault `Thinking/` scaffold | Via workspace config |

### Change (minimal)

| Path | Change |
|------|--------|
| `docs/ARCHITECTURE.md` / `PRODUCT_v1.md` | SoT banners |
| `backend/app/config.py` / `.env.example` | Notion token + database id |
| `backend/configs/workspace.yaml` | `thinking` / `information` / `research` folders |
| `backend/app/api.py` | `POST /api/thinking/sync` (Phase 5) |
| `backend/app/db.py` | Sync state table (Phase 5) |

### Do not rewrite

`content_lake.py`, collect connectors, `library_writer.py`, graph engine core, lifecycle maturity UX.

---

## 5. Phased delivery

| Phase | Status | Work |
|-------|--------|------|
| 1 Audit | Done | Reuse map |
| 2 Docs + Canonical model | **In progress** | Docs + `ThinkingObject` + tests; no Notion network |
| 3 Notion Adapter | Pending | Mocked properties JSON |
| 4 Obsidian Writer | Pending | `Thinking/*.md` |
| 5 Sync Engine | Pending | CLI + API; idempotent |
| 6 Graph | Deferred | Wikilink survival only |
| 7 Website | Deferred | Consume Obsidian-derived content |

---

## 6. Cutover

| Existing | V1 |
|----------|-----|
| `Reflections/*.md` | KEEP; not auto-moved |
| `Library/` | KEEP Information surface |
| New Notion Thinking | `Thinking/` only |

---

## 7. Gate before Phases 3–5

1. Architecture + Migration + Notion checklist on disk  
2. SoT banners present  
3. Canonical model tests green  
4. Token + database id plan agreed
