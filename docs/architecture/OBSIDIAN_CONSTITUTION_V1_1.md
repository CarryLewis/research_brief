# Obsidian Constitution V1.1

**Status:** Authoritative Obsidian-facing architecture  
**Date:** 2026-08  
**Conflict report:** [`OBSIDIAN_CONSTITUTION_CONFLICTS.md`](OBSIDIAN_CONSTITUTION_CONFLICTS.md)  
**Supersedes:** Constitution V1 Research Workspace folder/taxonomy rules; PRODUCT_v1 §7 `Library/{Articles,Emails,Books}` layout

This document is the Obsidian-facing constitution for Personal Observatory / Research Brief.  
Backend systems (Content Lake, Knowledge Database, Graph Engine projection tables, Website publish) may remain sophisticated. The vault must remain minimal.

---

## 1. Core philosophy

Obsidian is **not** the primary application UI, a knowledge-management bureaucracy, or a taxonomy system.

Obsidian **is**:

- local cognitive storage
- human-readable editing
- linking layer
- knowledge graph substrate

If the user must think about *where* or *how* to store something, the system has introduced unnecessary cognitive overhead.

Flow:

```text
Observe → Capture → Think → Connect → Synthesize
```

---

## 2. Cognitive vs system architecture

| Layer | Authority | May appear in Obsidian? |
|-------|-----------|-------------------------|
| Content Lake | Immutable bytes | No (attachments are technical exceptions only) |
| Knowledge Database | KO, edges, lifecycle, proposals | No as folders/tags/graph nodes |
| Graph Engine (JSON API) | Rebuildable cognitive projection | Not as infrastructure nodes |
| Obsidian vault | Human-readable cognitive objects + wikilinks | Yes — only Information / Thinking / Research |

`lifecycle_stage`, processing state, ingestion jobs, workspace plumbing, and API objects are **system** concepts. They must not become vault folders, required frontmatter, tags, or graph nodes.

---

## 3. Target vault

```text
Vault/
├── Information/     # external world: articles, papers, books, reports, observations
├── Thinking/        # personal experience, reflections, questions, fragments
├── Research/        # mature syntheses / Research Briefs
├── Archive/         # cold legacy only (not daily IA)
└── 90_Meta/         # system conventions only (not cognitive nodes)
```

No domain folders (`Medicine/`, `AI/`, `2026/`, …). Subject matter lives in **links**, not hierarchy.

Technical exception: media may live under `Information/Attachments/{id}/` (or similar). Attachments are not cognitive graph nodes.

---

## 4. Constitutional rules (summary)

| Rule | Statement |
|------|-----------|
| 01 Minimum structure | Only Information / Thinking / Research as cognitive roots |
| 02 Folder ≠ classification | Folders = object role, not topic |
| 03 Human-readable filenames | Natural titles; no INF-0001 / KO-id filenames unless unavoidable |
| 04 Minimal metadata | Machine-useful fields only; folder implies role |
| 05 Links create the graph | Explicit `[[wikilinks]]` are primary relationships |
| 06 Graph ≠ infrastructure | No folder/DB/pipeline/status/template nodes |
| 07 One node = one cognitive object | Article, thought, question, synthesis, … |
| 08 AI must not pollute the graph | Detect → explain → propose; user accepts non-obvious links |
| 09 Quality over density | Meaningful connectivity, not maximum connectivity |
| 10 Information ≠ Thinking | Keep external intake and personal thought distinct |
| 11 Research is synthesis | Emerges from Information + Thinking; not forced |
| 12 Preserve fragmentation | Thinking may stay incomplete; do not overwrite originals |
| 13 AI in Thinking | Interviewer / clarifier / archivist — not ghostwriter or taxonomist |
| 14 Vault human-readable | Markdown is canonical; not dependent on hidden DB state |
| 15 Obsidian ≠ workflow bureaucracy | Complexity stays in infrastructure |

Non-negotiable: prefer less structure, less metadata, more meaningful links, and preservation of the user’s actual thinking.

---

## 5. Object streams

### Information

What entered from the external world. Interaction: Discover → Read → Save → Search → Connect.  
Capture **writes readable notes** under `Information/`. Content Lake remains immutable byte authority for backend.

### Thinking

What the user experienced, noticed, questioned, or reflected. Interaction: Experience → Conversation → Clarification → Capture → Reflection → Connection.  
May begin as a fragment. AI may clarify; must not erase the original form.

### Research

Mature synthesis emerging from relationships between Information and Thinking. Not a third raw-capture dump. Research Briefs land here when synthesis is warranted — not for every object.

---

## 6. Metadata & tags

Preferred Information frontmatter (minimal):

```yaml
id: lib_…          # optional system id
title: …
source_url: …      # when applicable
captured_at: …     # system-generated
visibility: private # only if publish needs it
```

Do **not** require users to maintain type/status/domain/category/topic/maturity/workspace_role forms.  
Folder location implies cognitive role.  
Tags are optional and must not duplicate folder names, object types, or database states. Prefer wikilinks over tag taxonomies.

---

## 7. Graph

Desired shape:

```text
[Information A] --supports--> [Thinking B] --develops--> [Research C]
[Information D] --challenges--> [Research C]
```

Must **not** contain: Information/, Thinking/, Research/, Database/, Resource/, Workspace/, Pipeline/, API/, Template/, Status/ as cognitive nodes.

AI link suggestions require explicit accept/reject/ignore for non-obvious relationships. No automatic link explosions.

---

## 8. Capture & Inbox

No living `Inbox/`.

```text
Capture → Processing → Information / Thinking
```

Legacy Inbox / PreConstitution dumps stay under `Archive/` for recovery only.

---

## 9. Backend remapping (implementation contract)

| Legacy vault / role surface | V1.1 surface |
|-----------------------------|--------------|
| `Library/Articles\|Emails\|Books` | `Information/` |
| `Library/Notes`, `Reflections/` | `Thinking/` |
| `Concepts/`, idea-like `Projects/` | `Thinking/` (or Archive if unused) |
| Mature Insights / Research Briefs | `Research/` |
| `Reports/` digests | `Archive/Digests/` (not cognitive graph) |
| `Books/` reading cards | `Information/` |
| `workspace_role=resource` never sync | Information notes written by library/capture path |
| Promote to concept/project folders | Remap to cognitive folders; prefer link approval UX |

Natural filenames and “wikilinks only to existing notes” remain in force.

---

## 10. Migration principles

Do not blindly delete.

```text
Current vault → Classify → Information / Thinking / Research → Legacy Archive
```

Every move should be logged; originals remain recoverable under `Archive/`.

---

## 11. Validation

**Vault:** three cognitive roots understandable in seconds; human-readable filenames; minimal metadata; no domain folder forest.  
**Graph:** independent cognitive objects; explicit links; no infrastructure pollution; propose-only AI links.  
**Thinking:** fragments allowed; originals preserved; connections proposed not auto-forced.  
**Architecture:** conflicts documented; superseded rules marked; backend complexity separated from vault simplicity.

---

*When Obsidian-facing rules change, update this file and the conflict report first.*
