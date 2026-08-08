"""HTML / URL → clean article Markdown (readability-lxml + markdownify).

V1 Library capture parse step: extract main content, preserve headings /
lists / links / images, optionally download images and rewrite Markdown paths.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_md
from readability import Document

from app.utils import sanitize_filename

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36 ResearchBriefStudio/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
}
_DEFAULT_HEADERS = FETCH_HEADERS

_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_DATA_URI_RE = re.compile(r"^data:", re.I)


@dataclass
class ReadableImage:
    """One image referenced by the parsed article body."""

    original_url: str
    local_path: Path | None = None
    markdown_path: str | None = None
    alt: str = ""
    content_type: str | None = None
    bytes_written: int = 0
    error: str | None = None


@dataclass
class ReadableResult:
    """Clean reading payload ready for Library note writing."""

    title: str
    body_md: str
    byline: str | None = None
    canonical_url: str | None = None
    excerpt: str | None = None
    clean_html: str = ""
    images: list[ReadableImage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_html(
    html: str,
    *,
    base_url: str | None = None,
    download_images: bool = False,
    image_dir: Path | str | None = None,
    image_path_prefix: str = "",
    client: httpx.Client | None = None,
    max_images: int = 40,
) -> ReadableResult:
    """Parse raw HTML into clean Markdown.

    When ``download_images`` is True, images are fetched into ``image_dir``
    and Markdown ``![]()`` targets are rewritten to local relative paths.
    ``image_path_prefix`` is prepended to those relative paths (e.g. for
    Obsidian vault links like ``Attachments/abc/``).
    """
    html = html or ""
    if not html.strip():
        return ReadableResult(title="", body_md="", canonical_url=base_url)

    byline = _meta_content(html, ("author", "article:author", "byl"))
    excerpt = _meta_content(html, ("description", "og:description", "twitter:description"))
    canonical = base_url or _canonical_url(html) or None

    # Drop common page chrome before Readability so nav/footer noise
    # is less likely to ride along in short or lightly structured pages.
    prepared = _strip_chrome(html)
    doc = Document(prepared)
    title = _clean_title(doc.title() or "")
    clean_html = doc.summary(html_partial=True) or ""
    clean_html = _absolutize_urls(clean_html, canonical)
    body_md = _html_to_markdown(clean_html)
    body_md = _normalize_markdown(body_md)

    if not title:
        title = _first_heading(body_md) or (urlparse(canonical).path.rsplit("/", 1)[-1] if canonical else "") or "Untitled"

    images = _collect_images_from_markdown(body_md)
    if max_images >= 0:
        images = images[:max_images]

    if download_images and images:
        if image_dir is None:
            raise ValueError("image_dir is required when download_images=True")
        dest = Path(image_dir)
        dest.mkdir(parents=True, exist_ok=True)
        own_client = client is None
        http = client or httpx.Client(timeout=30.0, follow_redirects=True, headers=_DEFAULT_HEADERS)
        try:
            body_md, images = _download_and_rewrite_images(
                body_md,
                images,
                dest=dest,
                path_prefix=image_path_prefix,
                client=http,
                referer=canonical,
            )
        finally:
            if own_client:
                http.close()

    return ReadableResult(
        title=title.strip(),
        body_md=body_md,
        byline=byline,
        canonical_url=canonical,
        excerpt=excerpt,
        clean_html=clean_html,
        images=images,
        metadata={
            "parser": "readability-lxml+markdownify",
            "download_images": download_images,
            "image_count": len(images),
        },
    )


def parse_url(
    url: str,
    *,
    download_images: bool = False,
    image_dir: Path | str | None = None,
    image_path_prefix: str = "",
    client: httpx.Client | None = None,
    max_images: int = 40,
) -> ReadableResult:
    """Fetch a public URL and parse it into clean Markdown."""
    url = (url or "").strip()
    if not _is_http_url(url):
        return ReadableResult(
            title=f"Invalid URL: {url}",
            body_md="",
            canonical_url=url or None,
            metadata={"error": "Only http/https URLs are allowed"},
        )

    own_client = client is None
    http = client or httpx.Client(timeout=45.0, follow_redirects=True, headers=_DEFAULT_HEADERS)
    try:
        resp = http.get(url)
        resp.raise_for_status()
        final_url = str(resp.url)
        ctype = (resp.headers.get("content-type") or "").lower()
        if "html" not in ctype and not url.rstrip("/").endswith((".html", ".htm", "/")):
            text = resp.text
            return ReadableResult(
                title=urlparse(final_url).path.rsplit("/", 1)[-1] or final_url,
                body_md=text.strip(),
                canonical_url=final_url,
                metadata={"content_type": ctype, "note": "non-html response returned as text"},
            )
        return parse_html(
            resp.text,
            base_url=final_url,
            download_images=download_images,
            image_dir=image_dir,
            image_path_prefix=image_path_prefix,
            client=http,
            max_images=max_images,
        )
    except Exception as exc:  # noqa: BLE001
        return ReadableResult(
            title=f"Fetch failed: {url}",
            body_md="",
            canonical_url=url,
            metadata={"error": str(exc)},
        )
    finally:
        if own_client:
            http.close()


def _strip_chrome(html: str) -> str:
    """Remove navigation / chrome elements before Readability scoring."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    for tag in soup.find_all(["nav", "header", "footer", "aside"]):
        # Keep headers that look like the article title block inside <article>
        if tag.name == "header" and tag.find_parent("article") is not None:
            continue
        tag.decompose()
    for tag in soup.find_all(True):
        role = (tag.get("role") or "").lower()
        if role in {"navigation", "banner", "contentinfo", "complementary"}:
            tag.decompose()
            continue
        classes = " ".join(tag.get("class") or []).lower()
        tid = (tag.get("id") or "").lower()
        blob = f"{classes} {tid}"
        if any(
            hint in blob
            for hint in (
                "nav-menu",
                "site-nav",
                "global-nav",
                "cookie-banner",
                "newsletter-signup",
                "social-share",
                "share-buttons",
                "related-posts",
                "recommended-posts",
                "advertisement",
                "adsbox",
            )
        ):
            tag.decompose()
    return str(soup)


def _html_to_markdown(clean_html: str) -> str:
    if not clean_html.strip():
        return ""
    return html_to_md(
        clean_html,
        heading_style="ATX",
        bullets="-",
        strip=["script", "style", "noscript"],
        escape_asterisks=False,
        escape_underscores=False,
    )


def _absolutize_urls(html: str, base_url: str | None) -> str:
    if not html or not base_url:
        return html
    soup = BeautifulSoup(html, "lxml")
    for tag, attr in (("img", "src"), ("a", "href"), ("source", "src")):
        for el in soup.find_all(tag):
            val = el.get(attr)
            if not val or _DATA_URI_RE.match(val) or val.startswith("#"):
                continue
            el[attr] = urljoin(base_url, val)
    # Prefer lxml serializer body contents if wrapped
    body = soup.body
    if body is not None:
        return "".join(str(c) for c in body.contents)
    return str(soup)


def _collect_images_from_markdown(body_md: str) -> list[ReadableImage]:
    images: list[ReadableImage] = []
    seen: set[str] = set()
    for match in _MD_IMAGE_RE.finditer(body_md or ""):
        alt, src = match.group(1), match.group(2).strip()
        if not src or src in seen or _DATA_URI_RE.match(src):
            continue
        if not _is_http_url(src):
            continue
        seen.add(src)
        images.append(ReadableImage(original_url=src, alt=alt or ""))
    return images


def _download_and_rewrite_images(
    body_md: str,
    images: list[ReadableImage],
    *,
    dest: Path,
    path_prefix: str,
    client: httpx.Client,
    referer: str | None,
) -> tuple[str, list[ReadableImage]]:
    prefix = path_prefix.strip().replace("\\", "/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    url_to_md_path: dict[str, str] = {}
    headers = {}
    if referer:
        headers["Referer"] = referer

    for idx, image in enumerate(images, start=1):
        try:
            resp = client.get(image.original_url, headers=headers)
            resp.raise_for_status()
            content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            data = resp.content
            if not data:
                image.error = "empty image body"
                continue
            filename = _image_filename(image.original_url, content_type, idx, data)
            path = dest / filename
            # Avoid clobbering different bytes with same hint name
            if path.exists() and path.read_bytes() != data:
                stem, suffix = path.stem, path.suffix
                path = dest / f"{stem}_{hashlib.sha1(data).hexdigest()[:8]}{suffix}"
                filename = path.name
            path.write_bytes(data)
            md_path = f"{prefix}{filename}"
            image.local_path = path
            image.markdown_path = md_path
            image.content_type = content_type or None
            image.bytes_written = len(data)
            url_to_md_path[image.original_url] = md_path
        except Exception as exc:  # noqa: BLE001
            image.error = str(exc)

    def _replace(match: re.Match[str]) -> str:
        alt, src = match.group(1), match.group(2).strip()
        new_src = url_to_md_path.get(src)
        if not new_src:
            return match.group(0)
        return f"![{alt}]({new_src})"

    return _MD_IMAGE_RE.sub(_replace, body_md), images


def _image_filename(url: str, content_type: str, index: int, data: bytes) -> str:
    path = urlparse(url).path
    raw_name = path.rsplit("/", 1)[-1] if path else ""
    raw_name = raw_name.split("?")[0]
    stem = sanitize_filename(Path(raw_name).stem) if raw_name else ""
    ext = Path(raw_name).suffix.lower() if raw_name else ""
    if not ext or len(ext) > 5:
        guessed = mimetypes.guess_extension(content_type or "") or ""
        if guessed == ".jpe":
            guessed = ".jpg"
        ext = guessed or ".img"
    if not stem or stem == "untitled":
        digest = hashlib.sha1(data).hexdigest()[:10]
        stem = f"image_{index:02d}_{digest}"
    return f"{stem}{ext}"[:120]


def _normalize_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", (title or "").strip())
    # Common "Title | Site" / "Title - Site" tails: keep left if both sides look non-empty
    for sep in (" | ", " — ", " – ", " - "):
        if sep in title:
            left, right = title.split(sep, 1)
            if len(left.strip()) >= 4 and len(right.strip()) <= 40:
                return left.strip()
    return title


def _first_heading(body_md: str) -> str:
    for line in (body_md or "").splitlines():
        m = re.match(r"^#{1,6}\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()
    return ""


def _meta_content(html: str, names: tuple[str, ...]) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for name in names:
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if tag and tag.get("content"):
            value = re.sub(r"\s+", " ", tag["content"]).strip()
            if value:
                return value
    return None


def _canonical_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    link = soup.find("link", attrs={"rel": lambda v: v and "canonical" in str(v).lower()})
    if link and link.get("href"):
        href = link["href"].strip()
        if _is_http_url(href):
            return href
    og = soup.find("meta", attrs={"property": "og:url"})
    if og and og.get("content"):
        href = og["content"].strip()
        if _is_http_url(href):
            return href
    return None


def _is_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:  # noqa: BLE001
        return False
