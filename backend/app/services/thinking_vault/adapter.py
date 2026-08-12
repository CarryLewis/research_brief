"""Notion Adapter — fetch Thinking Database pages/properties/relations.

Does not know Obsidian Markdown shape.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .model import ThinkingObject
from .normalizer import (
    extract_relation_ids,
    extract_title,
    normalize_page,
    property_names,
)
from .notion_client import NotionClient

logger = logging.getLogger(__name__)


class NotionThinkingAdapter:
    """Read-only adapter: Notion DB → list[ThinkingObject]."""

    def __init__(
        self,
        client: NotionClient,
        database_id: str,
        *,
        property_cfg: dict[str, Any] | None = None,
        page_fetcher: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.client = client
        self.database_id = database_id
        self.property_cfg = property_cfg or {}
        self._page_fetcher = page_fetcher or client.retrieve_page
        self.names = property_names(self.property_cfg)

    def fetch_raw_pages(self) -> list[dict[str, Any]]:
        pages = list(self.client.iter_database_pages(self.database_id))
        logger.info("Notion adapter fetched %s pages from database", len(pages))
        return pages

    def build_title_index(self, pages: list[dict[str, Any]]) -> dict[str, str]:
        """Map page id → title for same-batch Wikilink resolution."""
        index: dict[str, str] = {}
        for page in pages:
            pid = str(page.get("id") or "").strip()
            if not pid:
                continue
            props = page.get("properties") or {}
            title = extract_title(props, self.names["title"])
            index[pid] = title
            index[pid.replace("-", "")] = title
        # Resolve relation targets not in this database query
        missing: set[str] = set()
        rel_prop = self.names["related_information"]
        for page in pages:
            props = page.get("properties") or {}
            for rid in extract_relation_ids(props, rel_prop):
                if rid not in index and rid.replace("-", "") not in index:
                    missing.add(rid)
        for rid in sorted(missing):
            try:
                remote = self._page_fetcher(rid)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to resolve relation page %s: %s", rid, exc)
                continue
            rprops = remote.get("properties") or {}
            # Related Information pages may use Title/Name
            title = extract_title(rprops, self.names["title"])
            if title == "Untitled":
                title = extract_title(rprops, "Title")
            if title and title != "Untitled":
                index[rid] = title
                index[rid.replace("-", "")] = title
            elif remote.get("id"):
                # Fall back to any title property already handled; keep Untitled only if needed
                index[rid] = title
                index[rid.replace("-", "")] = title
        return index

    def fetch_thinking_objects(self) -> list[ThinkingObject]:
        pages = self.fetch_raw_pages()
        title_index = self.build_title_index(pages)
        objects: list[ThinkingObject] = []
        for page in pages:
            try:
                obj = normalize_page(
                    page,
                    relation_titles=title_index,
                    property_cfg=self.property_cfg,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Normalization failed for Notion page %s: %s",
                    page.get("id"),
                    exc,
                )
                raise
            if not obj.source_id:
                logger.warning("Skipping Notion page without id: %s", page)
                continue
            objects.append(obj)
        return objects
