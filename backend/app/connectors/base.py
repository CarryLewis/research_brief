from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MediaAsset:
    url: str
    kind: str  # image | video | other
    filename_hint: str | None = None


@dataclass
class FetchedDoc:
    connector: str
    title: str
    raw_text: str
    url: str | None = None
    authors: str | None = None
    published_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "ready"
    error: str | None = None
    media: list[MediaAsset] = field(default_factory=list)


class BaseConnector:
    name: str = "base"

    def fetch(self, scope: dict[str, Any]) -> list[FetchedDoc]:
        raise NotImplementedError

    def passes_filters(self, doc: FetchedDoc, scope: dict[str, Any]) -> bool:
        text_blob = f"{doc.title}\n{doc.raw_text}".lower()
        must_include = [x.lower() for x in scope.get("must_include") or [] if x]
        must_exclude = [x.lower() for x in scope.get("must_exclude") or [] if x]
        if must_include and not all(term in text_blob for term in must_include):
            return False
        if must_exclude and any(term in text_blob for term in must_exclude):
            return False

        time_range = scope.get("time_range") or {}
        from_s = time_range.get("from") or time_range.get("from_")
        to_s = time_range.get("to")
        if doc.published_at and (from_s or to_s):
            try:
                pub = _parse_date(doc.published_at)
                if from_s and pub < _parse_date(from_s):
                    return False
                if to_s and pub > _parse_date(to_s):
                    return False
            except ValueError:
                pass
        return True


def _parse_date(value: str) -> datetime:
    value = value.strip()
    candidates = [value[:19], value[:10], value[:16]]
    formats = (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
    )
    for candidate in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    raise ValueError(f"Unrecognized date: {value}")
