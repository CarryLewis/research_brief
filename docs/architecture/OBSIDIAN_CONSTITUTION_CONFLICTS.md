# Obsidian Constitution V1.1 — Architecture Conflict Report

**Status:** Authoritative conflict reconciliation  
**Date:** 2026-08  
**Supersedes (Obsidian-facing):** Constitution V1 vault rules in [`ARCHITECTURE.md`](../ARCHITECTURE.md) §6; PRODUCT_v1 §7 Library layout  
**Canonical target:** [`OBSIDIAN_CONSTITUTION_V1_1.md`](OBSIDIAN_CONSTITUTION_V1_1.md)

Format: **Existing Rule → V1.1 Rule → Conflict → Decision → Required Change**

---

## Authority

| Existing | V1.1 | Conflict | Decision | Required change |
|----------|------|----------|----------|-----------------|
| PRODUCT_v1 is product SoT; ARCHITECTURE Constitution is historical | V1.1 is authoritative for all Obsidian-facing design | Dual SoT + hybrid vault | **MODIFY** | Point PRODUCT §7 and ARCHITECTURE §6 at V1.1; keep Lake/KO/Website as system architecture |
| README teaches Constitution forest + “Capture never mirrors” | Capture writes Information; vault = Information/Thinking/Research | Outdated operator narrative | **MODIFY** | Rewrite README vault section |

---

## Conflict A — Multiple workspace folders

| Existing | V1.1 | Conflict | Decision | Required change |
|----------|------|----------|----------|-----------------|
| Vault roots: Projects/ Concepts/ Books/ Reflections/ Insights/ Reports/ Collections/ | Only Information/ Thinking/ Research/ (+ cold Archive/, system 90_Meta/) | Typed forest vs three cognitive roles | **REMOVE** typed roots as user-facing | `workspace.yaml` folder map; `ensure_scaffold`; Welcome |
| PRODUCT `Library/{Articles,Emails,Books,Notes}/` | Flat `Information/` — medium ≠ folder | Medium taxonomy in folders | **MODIFY** | Retarget `library_writer` to `Information/` |
| `workspace_role` → Concepts/Projects/… | Folder = cognitive role only | Role forest leaked into vault | **MODIFY** | Keep `workspace_role` in DB; map sync path via cognitive folder |

---

## Conflict B — Knowledge Object taxonomy

| Existing | V1.1 | Conflict | Decision | Required change |
|----------|------|----------|----------|-----------------|
| Concept / Project / Reflection / Book / Report as vault note types | One node = one independent cognitive object; folders are role not type | Type folders = taxonomy | **DEPRECATE** vault exposure | Sync Concept/Project/Reflection → Thinking or Research; Book → Information; stop scaffolding type folders |
| Promote → concept/project/reflection/book notes | External → Information; personal → Thinking; mature synthesis → Research | Promote funnel as vault UX | **MODIFY** | Accept cognitive roles `information`/`thinking`/`research`; legacy promote roles remap to folders |
| Insights optional `Insights/` | Mature synthesis → `Research/` | Extra folder | **DEPRECATE** | Map insight sync → Research/ |
| Digest → `Reports/` (`graph: false`) | Digests are not cognitive Research by default | Reports root in vault | **DEPRECATE** as daily root | Write digests to `Archive/Digests/` or email/DB only |

---

## Conflict C — Automatic graph generation

| Existing | V1.1 | Conflict | Decision | Required change |
|----------|------|----------|----------|-----------------|
| Graph Engine rebuilds nodes from KO + KoLink; propose-only link suggestions | Propose meaningful relationships; no link explosions; no infrastructure nodes | Objective was coverage/views, not semantic restraint | **KEEP** propose-only; **MODIFY** objective | Document anti-pollution; default views = cognitive objects; exclude folder/status/pipeline nodes |
| Views: governance, with_resources, concept/project layers | Graph answers “what ideas/observations/information connect?” | Infrastructure-adjacent views as product surface | **MODIFY** | Default cognitive views; resources/reports not default graph nodes |
| Wikilinks only to existing workspace notes | Explicit intentional links | Aligned | **KEEP** | No inventing stub notes |

---

## Conflict D — Tags

| Existing | V1.1 | Conflict | Decision | Required change |
|----------|------|----------|----------|-----------------|
| Domain filter-tag allowlist (medicine, neurology, …) auto-normalized into notes | Tags must not become a second taxonomy | Domain tags = soft classification | **MODIFY / reduce** | Stop requiring allowlist on notes; do not emit folder/type/state tags; prefer wikilinks |
| Tag Taxonomy.md as vault teaching surface | Minimal cognitive overhead | Encourages taxonomy maintenance | **MODIFY** | Rewrite or shrink 90_Meta Tag Taxonomy |

---

## Conflict E — Frontmatter

| Existing | V1.1 | Conflict | Decision | Required change |
|----------|------|----------|----------|-----------------|
| Constitution notes: type, status, tags, graph | Folder implies cognitive role; minimal machine metadata | Manual schema burden | **MODIFY** | Slim templates: system timestamps / source_url / id when needed |
| Library notes: type, tags, visibility, status: inbox | Prefer inferred + system fields | status/inbox + type duplicate folder/medium | **MODIFY** | Keep `source_url`, `captured_at`, optional `id`/`visibility` for publish; drop required status/inbox/taxonomy tags |
| Artificial IDs in filenames | Human-readable filenames | Filenames already natural | **KEEP** | Continue natural stems; ids stay in frontmatter only if needed |

---

## Conflict F — Inbox / Capture

| Existing | V1.1 | Conflict | Decision | Required change |
|----------|------|----------|----------|-----------------|
| No living Inbox/ (Constitution already eliminated) | Capture → Processing → Information/Thinking | Aligned | **KEEP** | Do not reintroduce Inbox/ |
| Capture never writes vault (`sources_written=0`); Resources never sync | Information Library: Discover → Read → Save into vault | Direct contradiction with PRODUCT + V1.1 | **MODIFY** | Library/collect Information path writes readable notes under `Information/`; Lake remains byte SoT |
| PRODUCT “采集即入库” into Library | Same intent into Information/ | Path name only | **KEEP** intent; **MODIFY** path | Rename writer root |

---

## Backend vs cognitive separation

| Existing | V1.1 | Conflict | Decision | Required change |
|----------|------|----------|----------|-----------------|
| Content Lake | Backend storage; not a graph/folder node | None if not projected | **KEEP** | Never scaffold Lake paths into vault graph |
| Knowledge Database / KO / lifecycle_stage | System architecture | May remain | **KEEP** | Do not mirror stages as folders/tags/graph nodes |
| ConceptSuggestion / promote/demote | Useful intake; must not dump Concepts into vault automatically | AI pollution risk | **KEEP** propose; **MODIFY** materialization | Vault write only after user confirm into cognitive folder |
| Research Brief / Ask → Brief | Research emerges from Information + Thinking | Forcing every object into Research | **MODIFY** | Only mature syntheses → `Research/` |
| Reflections freeform + preserve original body | Preserve fragmentation (Rule 12) | Aligned | **KEEP** → Thinking/ | Map reflection sync to Thinking/ |
| AI never auto-creates Concept/Project/Reflection notes | AI proposes links; clarifies thinking; no autonomous organizer | Aligned spirit | **KEEP** | Conversational Thinking capture may write after confirm |
| Archive/Legacy / PreConstitution-Inbox | Cold recovery | Aligned | **KEEP** | Migration target only |
| Website publish (PRODUCT) | Out of Obsidian constitution scope | None | **KEEP** | Remap publish root Library → Information when implementing |

---

## Decision legend

| Decision | Meaning |
|----------|---------|
| **KEEP** | Remains authoritative as stated |
| **MODIFY** | Remains but must change behavior or surface |
| **DEPRECATE** | No longer authoritative; may linger in code/Archive until removed |
| **REMOVE** | Must not remain as user-facing architecture |

---

## Implementation checklist (from this report)

1. Publish V1.1 constitution + mark ARCHITECTURE §6 / PRODUCT §7 superseded  
2. Remap `workspace.yaml`, `library_writer`, `workspace.py`, collect/save paths  
3. Slim frontmatter + reduce tags  
4. Graph Engine cognitive default + propose-only links  
5. Non-destructive migrator → Information / Thinking / Research + Archive
