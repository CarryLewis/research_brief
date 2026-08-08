from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .base import BaseConnector, FetchedDoc, MediaAsset


class WebConnector(BaseConnector):
    """Fetch user-provided page URLs and collect text + media links."""

    name = "web"

    def fetch_urls(self, urls: list[str]) -> list[FetchedDoc]:
        """Fetch an explicit list of URLs (used by email inbound pipeline)."""
        return self.fetch({"connectors": {"web": {"urls": list(urls or [])}}})

    def fetch(self, scope: dict[str, Any]) -> list[FetchedDoc]:
        web = (scope.get("connectors") or {}).get("web") or {}
        urls = web.get("urls") or []
        docs: list[FetchedDoc] = []
        headers = {
            "User-Agent": "ResearchBriefStudio/0.1 (+local; respectful fetch)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        }
        with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
            for url in urls:
                url = (url or "").strip()
                if not url:
                    continue
                if not _is_http_url(url):
                    docs.append(
                        FetchedDoc(
                            connector=self.name,
                            title=f"Invalid URL: {url}",
                            raw_text="",
                            url=url,
                            status="failed",
                            error="Only http/https URLs are allowed",
                        )
                    )
                    continue
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    final_url = str(resp.url)
                    ctype = (resp.headers.get("content-type") or "").lower()
                    if "html" in ctype or url.rstrip("/").endswith((".html", ".htm")):
                        title, text, media = _html_extract(resp.text, final_url)
                    else:
                        title = urlparse(final_url).path.rsplit("/", 1)[-1] or final_url
                        text = resp.text
                        media = []
                    doc = FetchedDoc(
                        connector=self.name,
                        title=title or final_url,
                        raw_text=f"{title}\n\n{text}".strip(),
                        url=final_url,
                        metadata={"requested_url": url},
                        media=media,
                    )
                    if self.passes_filters(doc, scope):
                        docs.append(doc)
                except Exception as exc:  # noqa: BLE001
                    docs.append(
                        FetchedDoc(
                            connector=self.name,
                            title=f"Fetch failed: {url}",
                            raw_text="",
                            url=url,
                            status="failed",
                            error=str(exc),
                        )
                    )
        return docs


def _is_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:  # noqa: BLE001
        return False


def _html_extract(html: str, base_url: str) -> tuple[str, str, list[MediaAsset]]:
    title_m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""

    media: list[MediaAsset] = []
    for m in re.finditer(r"(?is)<img[^>]+src=['\"]([^'\"]+)['\"]", html):
        src = urljoin(base_url, m.group(1).strip())
        if _is_http_url(src):
            media.append(MediaAsset(url=src, kind="image", filename_hint=_name_from_url(src)))
    for m in re.finditer(r"(?is)<(?:source|video)[^>]+src=['\"]([^'\"]+)['\"]", html):
        src = urljoin(base_url, m.group(1).strip())
        if _is_http_url(src):
            kind = "video" if _looks_video(src) else "other"
            media.append(MediaAsset(url=src, kind=kind, filename_hint=_name_from_url(src)))
    for m in re.finditer(r"(?is)<a[^>]+href=['\"]([^'\"]+\.(?:mp4|webm|mov|m4v))['\"]", html):
        src = urljoin(base_url, m.group(1).strip())
        if _is_http_url(src):
            media.append(MediaAsset(url=src, kind="video", filename_hint=_name_from_url(src)))

    # dedupe media by url
    seen: set[str] = set()
    uniq: list[MediaAsset] = []
    for asset in media:
        if asset.url in seen:
            continue
        seen.add(asset.url)
        uniq.append(asset)

    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text[:30000], uniq[:40]


def _name_from_url(url: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] or "asset"
    return re.sub(r"[^\w.\-]+", "_", name)[:80]


def _looks_video(url: str) -> bool:
    lower = url.lower().split("?", 1)[0]
    return lower.endswith((".mp4", ".webm", ".mov", ".m4v", ".mkv"))
