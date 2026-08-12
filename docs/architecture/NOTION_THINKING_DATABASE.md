# Notion Thinking Database — Setup Checklist

**Status:** Human setup guide for Thinking Vault V1  
**Contract:** [`THINKING_VAULT_ARCHITECTURE.md`](THINKING_VAULT_ARCHITECTURE.md) §3

V1 does **not** auto-create this schema. Create one Notion Database and share it with your Internal Integration.

---

## 1. Integration

1. Create a Notion Internal Integration; copy the secret → `NOTION_TOKEN`.
2. Create (or open) the Thinking Database; copy its id → `NOTION_THINKING_DATABASE_ID`.
3. Invite the integration to the database (Share → Invite).

---

## 2. Required properties

Create these columns with **exact names** (or keep names and adjust the backend property map later):

| Property name | Notion type | Notes |
|---------------|-------------|-------|
| Name | Title | Required |
| Status | Select | Options: `Draft`, `Active`, `Archived` |
| Raw Thought | Rich text | Preserve; never silently overwrite |
| Context | Rich text | |
| Observation | Rich text | |
| Interpretation | Rich text | |
| Uncertainty | Rich text | |
| Questions | Rich text | One question per line preferred |
| Later Reflection | Rich text | |
| Related Information | Relation | Prefer relation to this same database |

`Created time` / `Last edited time` are automatic — enable if not visible.

**Do not add** domain / topic / priority / maturity / tag taxonomies in V1.

---

## 3. Status meanings

| Option | Meaning |
|--------|---------|
| Draft | Not synced to Obsidian |
| Active | Synced to `Thinking/` |
| Archived | Soft-archived under `Archive/Thinking/` |

Empty Status is treated like Active.

---

## 4. Capture habit

1. Capture / chat in Notion (page body or AI is fine for scratch).
2. Before expecting Obsidian update: ensure **Name** + at least **Raw Thought** (and other columns you care about) are filled.
3. Set Status to `Active`.
4. Run Sync (CLI/API) or wait for poll.

Page body is **not** the sync source.

---

## 5. Links

- Use **Related Information** to point at other Thinking pages (same DB).
- Sync renders them as `[[Page Name]]` under `## Connections`.
- Cross-linking Information/Library notes by title is best-effort in V1.
