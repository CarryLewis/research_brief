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
| `Thinking/` | Personal observations, reflections, questions, fragments. |
| `Research/` | Mature syntheses / Research Briefs. |
| `Archive/` | Cold legacy only — not for new thinking. |
| `90_Meta/` | System conventions — not cognitive graph nodes. |

No living `Inbox/`. No domain folders (`Medicine/`, `AI/`, …).

## Capture path

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
