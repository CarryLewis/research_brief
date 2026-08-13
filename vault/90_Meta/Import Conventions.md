---
title: Import Conventions
type: meta
updated: 2026-08-12
---

# Pipeline rules (not a writing checklist)

Constitution V1.1 — cognitive vault. These constrain capture/sync. They are **not** how you should write day to day.

## Where notes live

| Folder | Purpose |
|--------|---------|
| `Information/` | External world — readable captures. Flat. No medium subfolders required. |
| `Thinking/` | **Thinking Vault (priority):** Notion property-column sync (overwrites by `source_id`) + personal fragments. |
| `Research/` | Mature syntheses / Research Briefs. |
| `Archive/` | Cold legacy + soft-archived Thinking notes — not for new thinking. |
| `90_Meta/` | System conventions — not cognitive graph nodes. |

No living `Inbox/`. No domain folders (`Medicine/`, `AI/`, …).

## Thinking Vault path (Notion → Obsidian)

1. Capture / clarify in Notion Thinking Database (**property columns**)
2. `python -m app.cli.thinking_sync` or `POST /api/thinking/sync`
3. Notes land in `Thinking/{Name}.md` with minimal `source` / `source_id` frontmatter
4. `Related Information` → `## Connections` Wikilinks

See [`docs/architecture/THINKING_VAULT_ARCHITECTURE.md`](../../docs/architecture/THINKING_VAULT_ARCHITECTURE.md) and the Notion checklist.

## Capture path (Information / Knowledge OS)

1. Capture → Content Lake (bytes) + Knowledge Object (DB)
2. Readable body → `Information/` note (human-readable identity = filename)
3. Thinking capture → `Thinking/` (after confirm when AI-assisted)
4. AI may **propose** links; you accept / reject / ignore
5. Research Briefs → `Research/` when synthesis is warranted

Digests (if any) land under `Archive/Digests/` — not the cognitive graph.

## Note shapes

**Information** (minimal frontmatter):

```markdown
---
id: lib_…
title: "Natural Title"
source_url: …
captured_at: …
visibility: private
---

# Natural Title

Readable body…

## Highlights

## Notes
```

**Thinking** (fragments allowed):

```markdown
---
title: "Natural Title"
date: YYYY-MM-DD
---

# Natural Title

Write anything. Incomplete is fine.
```

## Links & tags

Explicit `[[wikilinks]]` create the cognitive graph.  
Tags are optional and must not duplicate folders, types, or database states.

Small filter vocabulary only (`medicine`, `neurology`, `research`, …).  
Do not use type tags like `paper` / `article` in frontmatter.

### Thinking Vault: Tags vs Context

| | **Context** | **Tags** |
|---|---|---|
| Notion | Text (`;` / `；`) | Multi-select `Tags` |
| Obsidian | `## Context` → `[[wikilink]]` | Page **footer** → `#tag` |
| Role | Thinking anchors (enter the graph) | Filter labels (search only) |

Rules: do not put Context phrases into Tags; do not invent free-form tags; AI must not infer Tags from Raw Thought / Context. Empty Tags omit the footer line (no `## Tags` section).
