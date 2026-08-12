"""Normalize property bags into Canonical Thinking Objects.

Adapter (Phase 3) should emit a plain dict with these keys; this module
does not speak Notion API types.
"""

from __future__ import annotations

from typing import Any, Mapping

from .model import ConnectionRef, ThinkingObject


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _questions_from_value(value: Any) -> list[str]:
    """Rich text or list → list of non-empty question lines."""
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            s = _as_str(item)
            if s:
                out.append(s)
        return out
    text = _as_str(value)
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _connections_from_value(value: Any) -> list[ConnectionRef]:
    if not value:
        return []
    if not isinstance(value, list):
        raise TypeError("connections must be a list of {title, source_id?} dicts or strings")
    out: list[ConnectionRef] = []
    for item in value:
        if isinstance(item, ConnectionRef):
            if item.title.strip():
                out.append(item)
            continue
        if isinstance(item, str):
            title = item.strip()
            if title:
                out.append(ConnectionRef(title=title))
            continue
        if isinstance(item, Mapping):
            title = _as_str(item.get("title") or item.get("name"))
            source_id = _as_str(item.get("source_id") or item.get("id"))
            if title:
                out.append(ConnectionRef(title=title, source_id=source_id))
            continue
        raise TypeError(f"unsupported connection item: {type(item)!r}")
    return out


def normalize_thinking_properties(props: Mapping[str, Any]) -> ThinkingObject:
    """Build a ThinkingObject from a property bag.

    Expected keys (all optional except title + source_id for a syncable page):
      title, source_id, source, created_at, updated_at, status,
      raw_thought, context, observation, interpretation, uncertainty,
      questions, later_reflection, connections
    """
    source_id = _as_str(props.get("source_id"))
    title = _as_str(props.get("title"))
    if not source_id:
        raise ValueError("source_id is required")
    if not title:
        raise ValueError("title is required")

    source = _as_str(props.get("source")) or "notion"

    return ThinkingObject(
        title=title,
        source_id=source_id,
        source=source,
        created_at=_as_str(props.get("created_at") or props.get("created")),
        updated_at=_as_str(props.get("updated_at") or props.get("updated")),
        status=_as_str(props.get("status")),
        raw_thought=_as_str(props.get("raw_thought")),
        context=_as_str(props.get("context")),
        observation=_as_str(props.get("observation")),
        interpretation=_as_str(props.get("interpretation")),
        uncertainty=_as_str(props.get("uncertainty")),
        questions=_questions_from_value(props.get("questions")),
        later_reflection=_as_str(props.get("later_reflection")),
        connections=_connections_from_value(props.get("connections")),
    )
