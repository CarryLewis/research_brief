"""Canonical Thinking Object contract for Thinking Vault V1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ...utils import content_hash

SOURCE_NOTION = "notion"

# Status values aligned with Notion Select options.
STATUS_DRAFT = "Draft"
STATUS_ACTIVE = "Active"
STATUS_ARCHIVED = "Archived"

# Empty status is treated like Active.
SYNCABLE_STATUSES = frozenset({"", STATUS_ACTIVE.lower(), STATUS_ACTIVE})
ARCHIVE_STATUSES = frozenset({STATUS_ARCHIVED.lower(), STATUS_ARCHIVED})
SKIP_STATUSES = frozenset({STATUS_DRAFT.lower(), STATUS_DRAFT})

# Ordered body sections written to Obsidian when non-empty.
BODY_SECTION_FIELDS: tuple[tuple[str, str], ...] = (
    ("raw_thought", "Raw Thought"),
    ("context", "Context"),
    ("observation", "Observation"),
    ("interpretation", "Interpretation"),
    ("uncertainty", "Uncertainty"),
    ("questions", "Questions"),
    ("later_reflection", "Later Reflection"),
    ("connections", "Connections"),
)


@dataclass(frozen=True)
class ConnectionRef:
    """A relation target resolved for Wikilink rendering."""

    title: str
    source_id: str = ""

    def wikilink(self) -> str:
        name = (self.title or "").strip()
        return f"[[{name}]]" if name else ""


@dataclass
class ThinkingObject:
    """Internal contract — not a user-facing form."""

    title: str
    source_id: str
    source: str = SOURCE_NOTION
    created_at: str = ""
    updated_at: str = ""
    status: str = ""
    raw_thought: str = ""
    context: str = ""
    observation: str = ""
    interpretation: str = ""
    uncertainty: str = ""
    questions: list[str] = field(default_factory=list)
    later_reflection: str = ""
    connections: list[ConnectionRef] = field(default_factory=list)

    def normalized_status(self) -> str:
        return (self.status or "").strip()

    def should_skip_sync(self) -> bool:
        return self.normalized_status().lower() in {s.lower() for s in SKIP_STATUSES}

    def should_archive(self) -> bool:
        return self.normalized_status().lower() in {s.lower() for s in ARCHIVE_STATUSES}

    def should_write_active(self) -> bool:
        if self.should_skip_sync() or self.should_archive():
            return False
        # empty or Active
        return True

    def non_empty_sections(self) -> list[tuple[str, str]]:
        """Return (heading, body) pairs for Markdown, omitting empties."""
        out: list[tuple[str, str]] = []
        for field_name, heading in BODY_SECTION_FIELDS:
            if field_name == "questions":
                body = "\n".join(q.strip() for q in self.questions if q and str(q).strip())
            elif field_name == "connections":
                links = [c.wikilink() for c in self.connections if c.wikilink()]
                body = "\n".join(links)
            else:
                body = str(getattr(self, field_name) or "").strip()
            if body:
                out.append((heading, body))
        return out

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def thinking_content_hash(obj: ThinkingObject) -> str:
    """Stable hash for idempotent sync (excludes volatile formatting only)."""
    parts = [
        obj.source,
        obj.source_id,
        obj.title.strip(),
        obj.normalized_status(),
        obj.created_at.strip(),
        obj.updated_at.strip(),
        obj.raw_thought.strip(),
        obj.context.strip(),
        obj.observation.strip(),
        obj.interpretation.strip(),
        obj.uncertainty.strip(),
        "\n".join(q.strip() for q in obj.questions if q.strip()),
        obj.later_reflection.strip(),
        "\n".join(
            f"{c.source_id}:{c.title.strip()}" for c in obj.connections if c.title.strip()
        ),
    ]
    return content_hash("\n".join(parts))
