"""Normalize Notion property payloads into Canonical Thinking Objects."""

from __future__ import annotations

from typing import Any

from .model import ThinkingConnection, ThinkingObject


DEFAULT_PROPERTY_NAMES: dict[str, str] = {
    "title": "Name",
    "status": "Status",
    "raw_thought": "Raw Thought",
    "context": "Context",
    "observation": "Observation",
    "interpretation": "Interpretation",
    "uncertainty": "Uncertainty",
    "questions": "Questions",
    "later_reflection": "Later Reflection",
    "related_information": "Related Information",
}


def property_names(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    names = dict(DEFAULT_PROPERTY_NAMES)
    if cfg:
        override = cfg.get("property_names") or {}
        for key, value in override.items():
            if value:
                names[key] = str(value)
    return names


def rich_text_to_plain(rich_text: list[dict[str, Any]] | None) -> str:
    """Flatten Notion rich_text arrays to plain text (preserve newlines)."""
    if not rich_text:
        return ""
    parts: list[str] = []
    for block in rich_text:
        if not isinstance(block, dict):
            continue
        text = block.get("plain_text")
        if text is None and isinstance(block.get("text"), dict):
            text = block["text"].get("content")
        if text:
            parts.append(str(text))
    return "".join(parts).strip()


def extract_title(properties: dict[str, Any], title_prop: str = "Name") -> str:
    prop = properties.get(title_prop) or {}
    if prop.get("type") == "title":
        return rich_text_to_plain(prop.get("title")) or "Untitled"
    # Fallback: first title-typed property
    for value in properties.values():
        if isinstance(value, dict) and value.get("type") == "title":
            return rich_text_to_plain(value.get("title")) or "Untitled"
    return "Untitled"


def extract_rich_text_prop(properties: dict[str, Any], name: str) -> str:
    prop = properties.get(name)
    if not isinstance(prop, dict):
        return ""
    ptype = prop.get("type")
    if ptype == "rich_text":
        return rich_text_to_plain(prop.get("rich_text"))
    if ptype == "title":
        return rich_text_to_plain(prop.get("title"))
    return ""


def extract_select_prop(properties: dict[str, Any], name: str) -> str:
    prop = properties.get(name)
    if not isinstance(prop, dict):
        return ""
    if prop.get("type") == "select":
        sel = prop.get("select") or {}
        return str(sel.get("name") or "").strip()
    if prop.get("type") == "status":
        sel = prop.get("status") or {}
        return str(sel.get("name") or "").strip()
    return ""


def extract_relation_ids(properties: dict[str, Any], name: str) -> list[str]:
    prop = properties.get(name)
    if not isinstance(prop, dict) or prop.get("type") != "relation":
        return []
    out: list[str] = []
    for item in prop.get("relation") or []:
        if isinstance(item, dict) and item.get("id"):
            out.append(str(item["id"]))
    return out


def notion_datetime(page: dict[str, Any], *, created: bool) -> str:
    key = "created_time" if created else "last_edited_time"
    return str(page.get(key) or "").strip()


def normalize_page(
    page: dict[str, Any],
    *,
    relation_titles: dict[str, str] | None = None,
    property_cfg: dict[str, Any] | None = None,
) -> ThinkingObject:
    """Convert one Notion page JSON into a ThinkingObject.

    `relation_titles` maps related page id → current title for Wikilinks.
    """
    names = property_names(property_cfg)
    props = page.get("properties") or {}
    if not isinstance(props, dict):
        props = {}

    title = extract_title(props, names["title"])
    connections: list[ThinkingConnection] = []
    title_index = relation_titles or {}
    for rel_id in extract_relation_ids(props, names["related_information"]):
        rel_title = (title_index.get(rel_id) or title_index.get(_strip_dashes(rel_id)) or "").strip()
        if not rel_title:
            # Keep id-backed placeholder only if title unknown — skip empty titles
            continue
        connections.append(ThinkingConnection(title=rel_title, source_id=rel_id))

    return ThinkingObject(
        title=title,
        source="notion",
        source_id=str(page.get("id") or "").strip(),
        created_at=notion_datetime(page, created=True),
        updated_at=notion_datetime(page, created=False),
        raw_thought=extract_rich_text_prop(props, names["raw_thought"]),
        context=extract_rich_text_prop(props, names["context"]),
        observation=extract_rich_text_prop(props, names["observation"]),
        interpretation=extract_rich_text_prop(props, names["interpretation"]),
        uncertainty=extract_rich_text_prop(props, names["uncertainty"]),
        questions=extract_rich_text_prop(props, names["questions"]),
        later_reflection=extract_rich_text_prop(props, names["later_reflection"]),
        connections=connections,
        status=extract_select_prop(props, names["status"]),
    )


def _strip_dashes(value: str) -> str:
    return (value or "").replace("-", "")
