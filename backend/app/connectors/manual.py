from __future__ import annotations

from typing import Any

from .base import BaseConnector, FetchedDoc


class ManualConnector(BaseConnector):
    """Manual paste / file import — documents are provided by the API, not fetched."""

    name = "manual"

    def fetch(self, scope: dict[str, Any]) -> list[FetchedDoc]:
        return []

    def from_payload(
        self,
        title: str,
        text: str,
        url: str | None = None,
        authors: str | None = None,
        published_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FetchedDoc:
        return FetchedDoc(
            connector=self.name,
            title=title or "Untitled",
            raw_text=text,
            url=url,
            authors=authors,
            published_at=published_at,
            metadata=metadata or {},
        )
