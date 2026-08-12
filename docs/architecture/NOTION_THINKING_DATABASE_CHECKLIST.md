# Notion Thinking Database — Manual Setup Checklist

**Purpose:** Create the Notion database that Thinking Vault V1 syncs from.  
**Contract:** Property columns are the content source of truth. Page body is not synced in V1.

Do **not** auto-create this schema from the API in V1 — set it up once by hand.

---

## 1. Create the database

1. In Notion, create a full-page database named e.g. **Thinking**.
2. Copy the database id from the URL (`notion.so/.../<database_id>?v=...`) into `.env` as `NOTION_THINKING_DATABASE_ID` (32 hex chars; dashes optional).
3. Create an internal integration at [Notion My Integrations](https://www.notion.so/my-integrations), copy the secret into `NOTION_TOKEN`.
4. Share the Thinking database (and any related Information DB if used) with that integration.

---

## 2. Required properties (exact default names)

Use these **display names** unless you override `thinking_vault.property_names` in [`backend/configs/workspace.yaml`](../../backend/configs/workspace.yaml).

| Property name | Notion type | Notes |
|---------------|-------------|-------|
| Name | Title | Default title property (rename to `Name` if needed) |
| Created | Created time | Built-in or Created time property |
| Updated | Last edited time | Built-in last edited time |
| Status | Select | Keep options few (e.g. `raw`, `developing`, `connected`) |
| Raw Thought | Rich text | Original expression — never overwritten by AI polish |
| Context | Rich text | Optional |
| Observation | Rich text | Optional |
| Interpretation | Rich text | Optional |
| Uncertainty | Rich text | Optional |
| Questions | Rich text | Optional; bullet lines OK |
| Later Reflection | Rich text | Optional |
| Related Information | Relation | Link to other Thinking pages and/or Information pages |

---

## 3. Do not add (V1)

- Domain / category / subcategory / topic / subtopic
- Priority / maturity / knowledge type / workspace / project / concept taxonomies
- Dozens of tags as sync-critical columns

The database is an **index of thinking slots**, not an ontology.

---

## 4. How content reaches Obsidian

```text
Fill property columns on a Thinking page
        ↓
POST /api/thinking/sync  or  python -m app.cli.thinking_sync
        ↓
Thinking/{Name}.md
```

- Empty properties → section omitted
- `Related Information` → `## Connections` with `[[Target Name]]`
- Identity = Notion page id (`source_id` in frontmatter), not filename

---

## 5. Conversation vs properties

Notion AI chat may happen in the page body. Until you (or a workflow) copy structured fields into the property columns above, Sync will not see that content.

Recommended habit: after clarify, put Raw Thought + structured fields into the columns, then sync.
