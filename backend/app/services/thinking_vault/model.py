"""Canonical Thinking Object for Thinking Vault V1 (property-column contract)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Status values used by the live Thinking valut DB.
STATUS_RAW = "raw"
STATUS_DEVELOPING = "developing"
STATUS_CONNECTED = "connected"
STATUS_FOLDER = "folder"

SECTION_FIELDS: tuple[str, ...] = (
    "raw_thought",
    "context",
    "observation",
    "interpretation",
    "uncertainty",
    "questions",
    "later_reflection",
)

SECTION_HEADINGS: dict[str, str] = {
    "raw_thought": "Raw Thought",
    "context": "Context",
    "observation": "Observation",
    "interpretation": "Interpretation",
    "uncertainty": "Uncertainty",
    "questions": "Questions",
    "later_reflection": "Later Reflection",
}

# Notion page body (blocks) → Obsidian section; not a database property.
PAGE_BODY_HEADING = "Extended Reflection"


@dataclass
class ThinkingConnection:
    """A link target resolved for Obsidian Wikilinks."""

    title: str
    source_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "source_id": self.source_id}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ThinkingConnection:
        data = data or {}
        return cls(
            title=str(data.get("title") or "").strip(),
            source_id=str(data.get("source_id") or "").strip(),
        )


@dataclass
class ThinkingObject:
    """Internal Thinking Object — not a user-facing metadata form."""

    title: str
    source: str = "notion"
    source_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    raw_thought: str = ""
    context: str = ""
    observation: str = ""
    interpretation: str = ""
    uncertainty: str = ""
    questions: str = ""
    later_reflection: str = ""
    page_body: str = ""
    connections: list[ThinkingConnection] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: str = ""

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip() or "Untitled"
        self.source = (self.source or "notion").strip() or "notion"
        self.source_id = (self.source_id or "").strip()
        self.created_at = (self.created_at or "").strip()
        self.updated_at = (self.updated_at or "").strip()
        self.status = (self.status or "").strip()
        self.page_body = (self.page_body or "").strip()
        for name in SECTION_FIELDS:
            setattr(self, name, (getattr(self, name) or "").strip())
        cleaned: list[ThinkingConnection] = []
        for conn in self.connections or []:
            if isinstance(conn, ThinkingConnection):
                if conn.title.strip():
                    cleaned.append(
                        ThinkingConnection(
                            title=conn.title.strip(),
                            source_id=(conn.source_id or "").strip(),
                        )
                    )
            elif isinstance(conn, dict):
                item = ThinkingConnection.from_dict(conn)
                if item.title:
                    cleaned.append(item)
        self.connections = cleaned
        tag_seen: set[str] = set()
        cleaned_tags: list[str] = []
        for raw in self.tags or []:
            tag = str(raw or "").strip()
            if not tag or tag in tag_seen:
                continue
            tag_seen.add(tag)
            cleaned_tags.append(tag)
        self.tags = cleaned_tags

    def is_folder(self) -> bool:
        """Status=folder → Obsidian real directory; body props stay Notion-only."""
        return self.status.casefold() == STATUS_FOLDER

    def content_fingerprint(self) -> str:
        """Stable hash input for idempotent sync.

        Folder pages ignore thinking properties / page body / tags — only title,
        status, and Related Information membership affect Obsidian.
        """
        if self.is_folder():
            parts = [
                self.title,
                self.source_id,
                self.created_at,
                self.updated_at,
                self.status,
            ]
            for conn in self.connections:
                parts.append(f"{conn.source_id}:{conn.title}")
            return "\n".join(parts)

        parts = [
            self.title,
            self.source_id,
            self.created_at,
            self.updated_at,
            self.status,
            self.raw_thought,
            self.context,
            self.observation,
            self.interpretation,
            self.uncertainty,
            self.questions,
            self.later_reflection,
            self.page_body,
        ]
        for conn in self.connections:
            parts.append(f"{conn.source_id}:{conn.title}")
        if self.tags:
            parts.append("tags:" + ",".join(self.tags))
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ThinkingObject:
        data = dict(data or {})
        connections_raw = data.pop("connections", []) or []
        allowed = set(cls.__dataclass_fields__.keys())
        connections = [
            c if isinstance(c, ThinkingConnection) else ThinkingConnection.from_dict(c)
            for c in connections_raw
        ]
        kwargs = {k: v for k, v in data.items() if k in allowed}
        return cls(connections=connections, **kwargs)
