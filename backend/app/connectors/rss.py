from __future__ import annotations

from typing import Any

import feedparser

from .base import BaseConnector, FetchedDoc


class RssConnector(BaseConnector):
    """RSS / Atom / Substack feeds."""

    name = "rss"

    def fetch(self, scope: dict[str, Any]) -> list[FetchedDoc]:
        rss = (scope.get("connectors") or {}).get("rss") or {}
        feeds = rss.get("feeds") or []
        max_per_feed = int(rss.get("max_per_feed") or 10)
        docs: list[FetchedDoc] = []
        for feed_url in feeds:
            if not feed_url:
                continue
            try:
                parsed = feedparser.parse(feed_url)
            except Exception as exc:  # noqa: BLE001
                docs.append(
                    FetchedDoc(
                        connector=self.name,
                        title=f"Feed error: {feed_url}",
                        raw_text="",
                        url=feed_url,
                        status="failed",
                        error=str(exc),
                    )
                )
                continue
            for entry in parsed.entries[:max_per_feed]:
                title = getattr(entry, "title", None) or "Untitled"
                summary = getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
                content = ""
                if getattr(entry, "content", None):
                    try:
                        content = entry.content[0].get("value", "")
                    except Exception:  # noqa: BLE001
                        content = ""
                body = _strip_html(content or summary)
                link = getattr(entry, "link", None)
                authors = None
                if getattr(entry, "author", None):
                    authors = entry.author
                published = getattr(entry, "published", None) or getattr(entry, "updated", None)
                if published and hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        t = entry.published_parsed
                        published = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
                    except Exception:  # noqa: BLE001
                        pass
                doc = FetchedDoc(
                    connector=self.name,
                    title=title,
                    raw_text=f"{title}\n\n{body}".strip(),
                    url=link,
                    authors=authors,
                    published_at=str(published)[:32] if published else None,
                    metadata={"feed": feed_url},
                )
                if self.passes_filters(doc, scope):
                    docs.append(doc)
        return docs


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
