---
title: Import Conventions
type: meta
tags:
  - meta
updated: 2026-08-02
---

# Pipeline rules (not a writing checklist)

These constrain capture/sync. They are **not** how you should write day to day.

## Where to write

| Folder | Purpose |
|--------|---------|
| `Thinking/` | **Thinking Vault (priority):** Notion property-column sync. Overwritten by sync on `source_id`. |
| `Information/` / `Research/` | Target cognitive roots (Information may still live under `Library/` transitionally). |
| `Reflections/` | Legacy freeform thinking. Title + body. System will not wipe your file on bulk Constitution sync. |
| `Concepts/` / `Projects/` / `Books/` | Slim structured notes after ideas settle. Your `## Notes` section is preserved on sync. |
| `Collections/` | Human indexes only |
| `Archive/` | Legacy dumps / soft-archived Thinking notes — not for new thinking |

## Thinking Vault path (Notion → Obsidian)

1. Capture / clarify in Notion Thinking Database (**property columns**)
2. `python -m app.cli.thinking_sync` or `POST /api/thinking/sync`
3. Notes land in `Thinking/{Name}.md` with minimal `source` / `source_id` frontmatter
4. `Related Information` → `## Connections` Wikilinks

See [`docs/architecture/THINKING_VAULT_ARCHITECTURE.md`](../../docs/architecture/THINKING_VAULT_ARCHITECTURE.md) and the Notion checklist.

## Capture path (Information / Knowledge OS)

1. Capture → Content Lake + Resource KO (**database only**)
2. AI may summarize & suggest Concepts (**database only**)
3. You promote → a vault note appears
4. Digests → `Reports/` (`graph: false`)

Articles, papers, RSS, emails stay **Resources** in the DB. Do not re-import them into the vault.

## Note shapes

**Reflection** (freeform):

```markdown
---
title: "Natural Title"
type: reflection
date: YYYY-MM-DD
graph: true
---

# Natural Title

Write anything.
```

**Concept / Project / Book** (slim):

```markdown
## Summary
## Key Ideas
## Connections
## Notes          ← your thinking (preserved on sync)
## References     ← URLs only, never lake: ids
```

## Tags

Small filter vocabulary only (`medicine`, `neurology`, `research`, …).  
Do not use type tags like `paper` / `article` in frontmatter.
