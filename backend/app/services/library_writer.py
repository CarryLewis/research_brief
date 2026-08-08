"""Write Library notes into the Obsidian vault (PRODUCT_v1).

Layout:
  Library/Articles/     — article notes
  Library/Emails/       — email notes (same template, type: email)
  Library/Books/        — book cards (later)
  Library/Attachments/{id}/ — local media for an item

Article notes follow PRODUCT_v1 §7.2: frontmatter + body + Highlights + Notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
import yaml

from app.services import readable as readable_svc
from app.utils import new_id

LibraryType = Literal["article", "email", "book"]
OnDuplicate = Literal["update", "skip", "new"]

LIBRARY_ROOT = "Library"
FOLDER_BY_TYPE: dict[str, str] = {
    "article": "Articles",
    "email": "Emails",
    "book": "Books",
}
ATTACHMENTS_FOLDER = "Attachments"

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


@dataclass
class LibraryItem:
    """Payload for one Library note."""

    title: str
    body_md: str
    source_type: LibraryType = "article"
    canonical_url: str | None = None
    authors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    visibility: str = "private"
    status: str = "inbox"
    captured_at: str | None = None
    published_at: str | None = None
    item_id: str | None = None
    highlights: list[str] = field(default_factory=list)
    notes_md: str = ""
    extra_frontmatter: dict[str, Any] = field(default_factory=dict)


@dataclass
class LibraryWriteResult:
    item_id: str
    note_path: Path
    note_relpath: str
    attachments_dir: Path
    created: bool
    updated: bool
    skipped: bool
    title: str
    source_url: str | None = None
    images_downloaded: int = 0
    image_errors: list[str] = field(default_factory=list)


def ensure_library_scaffold(vault: Path | str) -> Path:
    """Create Library/Articles|Emails|Books|Attachments (+ Notes)."""
    root = Path(vault).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    lib = root / LIBRARY_ROOT
    for name in (*FOLDER_BY_TYPE.values(), ATTACHMENTS_FOLDER, "Notes"):
        (lib / name).mkdir(parents=True, exist_ok=True)
    return root


def attachments_dir_for(vault: Path | str, item_id: str) -> Path:
    return Path(vault).expanduser() / LIBRARY_ROOT / ATTACHMENTS_FOLDER / item_id


def attachment_markdown_prefix(item_id: str) -> str:
    """Relative path from Library/Articles|Emails|Books note → Attachments/{id}/."""
    return f"../{ATTACHMENTS_FOLDER}/{item_id}"


def write_article(
    vault_path: str | Path,
    item: LibraryItem,
    *,
    on_duplicate: OnDuplicate = "update",
) -> LibraryWriteResult:
    """Write (or update) one article/email note. Does not fetch or parse HTML."""
    if item.source_type not in FOLDER_BY_TYPE:
        raise ValueError(f"Unsupported source_type: {item.source_type}")

    vault = ensure_library_scaffold(vault_path)
    existing = None
    if item.canonical_url and on_duplicate != "new":
        existing = find_by_source_url(vault, item.canonical_url, source_type=item.source_type)

    if existing and on_duplicate == "skip":
        meta, _ = _split_frontmatter(existing.read_text(encoding="utf-8"))
        item_id = str(meta.get("id") or item.item_id or new_id("lib"))
        url_val = meta.get("source_url")
        return LibraryWriteResult(
            item_id=item_id,
            note_path=existing,
            note_relpath=str(existing.relative_to(vault)),
            attachments_dir=attachments_dir_for(vault, item_id),
            created=False,
            updated=False,
            skipped=True,
            title=str(meta.get("title") or item.title),
            source_url=str(url_val).strip() if isinstance(url_val, str) and url_val.strip() else item.canonical_url,
        )

    if existing and on_duplicate == "update":
        meta, body = _split_frontmatter(existing.read_text(encoding="utf-8"))
        item_id = str(item.item_id or meta.get("id") or new_id("lib"))
        preserved_highlights = _section_body(body, "Highlights")
        preserved_notes = _section_body(body, "Notes")
        if not item.highlights and preserved_highlights.strip():
            item.highlights = _bullets_to_list(preserved_highlights)
        if not item.notes_md.strip() and preserved_notes.strip():
            item.notes_md = preserved_notes.strip()
        item.item_id = item_id
        if not item.captured_at and meta.get("captured_at"):
            item.captured_at = str(meta["captured_at"])
        note_path = existing
        created, updated = False, True
    else:
        item_id = item.item_id or new_id("lib")
        item.item_id = item_id
        folder = vault / LIBRARY_ROOT / FOLDER_BY_TYPE[item.source_type]
        folder.mkdir(parents=True, exist_ok=True)
        note_path = _unique_note_path(folder, item.title)
        created, updated = True, False

    if not item.captured_at:
        item.captured_at = _now_iso()

    attach_dir = attachments_dir_for(vault, item_id)
    attach_dir.mkdir(parents=True, exist_ok=True)

    note_path.write_text(render_library_note(item), encoding="utf-8")
    return LibraryWriteResult(
        item_id=item_id,
        note_path=note_path,
        note_relpath=str(note_path.relative_to(vault)),
        attachments_dir=attach_dir,
        created=created,
        updated=updated,
        skipped=False,
        title=item.title,
        source_url=item.canonical_url,
    )


def write_article_from_html(
    vault_path: str | Path,
    html: str,
    *,
    base_url: str | None = None,
    title: str | None = None,
    authors: list[str] | None = None,
    tags: list[str] | None = None,
    download_images: bool = True,
    on_duplicate: OnDuplicate = "update",
    client: httpx.Client | None = None,
    source_type: LibraryType = "article",
    visibility: str = "private",
    status: str = "inbox",
) -> LibraryWriteResult:
    """Parse HTML → Markdown, download images into Attachments/{id}/, write Library note."""
    vault = ensure_library_scaffold(vault_path)

    # Resolve id early so image relative paths are stable.
    existing = None
    if base_url and on_duplicate != "new":
        existing = find_by_source_url(vault, base_url, source_type=source_type)
    if existing and on_duplicate == "skip":
        meta, _ = _split_frontmatter(existing.read_text(encoding="utf-8"))
        item_id = str(meta.get("id") or new_id("lib"))
        url_val = meta.get("source_url")
        skip_url = (
            str(url_val).strip()
            if isinstance(url_val, str) and url_val.strip()
            else base_url
        )
        return LibraryWriteResult(
            item_id=item_id,
            note_path=existing,
            note_relpath=str(existing.relative_to(vault)),
            attachments_dir=attachments_dir_for(vault, item_id),
            created=False,
            updated=False,
            skipped=True,
            title=str(meta.get("title") or title or ""),
            source_url=skip_url,
        )

    if existing:
        meta, _ = _split_frontmatter(existing.read_text(encoding="utf-8"))
        item_id = str(meta.get("id") or new_id("lib"))
    else:
        item_id = new_id("lib")

    attach_dir = attachments_dir_for(vault, item_id)
    parsed = readable_svc.parse_html(
        html,
        base_url=base_url,
        download_images=download_images,
        image_dir=attach_dir if download_images else None,
        image_path_prefix=attachment_markdown_prefix(item_id) if download_images else "",
        client=client,
    )

    author_list = list(authors or [])
    if not author_list and parsed.byline:
        author_list = [parsed.byline]

    item = LibraryItem(
        title=(title or parsed.title or "Untitled").strip(),
        body_md=parsed.body_md,
        source_type=source_type,
        canonical_url=parsed.canonical_url or base_url,
        authors=author_list,
        tags=list(tags or []),
        item_id=item_id,
        visibility=visibility or "private",
        status=status or "inbox",
    )
    result = write_article(vault, item, on_duplicate=on_duplicate)
    result.images_downloaded = sum(1 for img in parsed.images if img.local_path and not img.error)
    result.image_errors = [f"{img.original_url}: {img.error}" for img in parsed.images if img.error]
    return result


def write_article_from_url(
    vault_path: str | Path,
    url: str,
    *,
    title: str | None = None,
    authors: list[str] | None = None,
    tags: list[str] | None = None,
    download_images: bool = True,
    on_duplicate: OnDuplicate = "update",
    client: httpx.Client | None = None,
    visibility: str = "private",
    status: str = "inbox",
) -> LibraryWriteResult:
    """Fetch URL → parse → write Library/Articles note (public pages only)."""
    url = (url or "").strip()
    vault = ensure_library_scaffold(vault_path)

    if on_duplicate != "new":
        existing = find_by_source_url(vault, url, source_type="article")
        if existing and on_duplicate == "skip":
            meta, _ = _split_frontmatter(existing.read_text(encoding="utf-8"))
            item_id = str(meta.get("id") or new_id("lib"))
            return LibraryWriteResult(
                item_id=item_id,
                note_path=existing,
                note_relpath=str(existing.relative_to(vault)),
                attachments_dir=attachments_dir_for(vault, item_id),
                created=False,
                updated=False,
                skipped=True,
                title=str(meta.get("title") or title or ""),
                source_url=url,
            )

    own_client = client is None
    http = client or httpx.Client(
        timeout=45.0,
        follow_redirects=True,
        headers=readable_svc.FETCH_HEADERS,
    )
    try:
        resp = http.get(url)
        resp.raise_for_status()
        final_url = str(resp.url)
        return write_article_from_html(
            vault,
            resp.text,
            base_url=final_url,
            title=title,
            authors=authors,
            tags=tags,
            download_images=download_images,
            on_duplicate=on_duplicate,
            client=http,
            source_type="article",
            visibility=visibility,
            status=status,
        )
    finally:
        if own_client:
            http.close()


def save(
    vault_path: str | Path,
    *,
    html: str | None = None,
    url: str | None = None,
    body_md: str | None = None,
    title: str | None = None,
    authors: list[str] | None = None,
    tags: list[str] | None = None,
    source_type: LibraryType = "article",
    visibility: str = "private",
    status: str = "inbox",
    download_images: bool = True,
    on_duplicate: OnDuplicate = "update",
    client: httpx.Client | None = None,
) -> LibraryWriteResult:
    """Unified Library save used by ``POST /api/library/save``.

    Priority: ``body_md`` → ``html`` (+ optional url as base) → ``url`` fetch.
    """
    if on_duplicate not in {"update", "skip", "new"}:
        raise ValueError("on_duplicate must be update, skip, or new")
    if source_type not in FOLDER_BY_TYPE:
        raise ValueError(f"Unsupported source_type: {source_type}")

    html_s = (html or "").strip() or None
    url_s = (url or "").strip() or None
    md_s = (body_md or "").strip() or None
    if not html_s and not url_s and not md_s:
        raise ValueError("Provide html, url, and/or body_md")

    if md_s:
        item = LibraryItem(
            title=(title or "Untitled").strip() or "Untitled",
            body_md=md_s,
            source_type=source_type,
            canonical_url=url_s,
            authors=list(authors or []),
            tags=list(tags or []),
            visibility=visibility or "private",
            status=status or "inbox",
        )
        return write_article(vault_path, item, on_duplicate=on_duplicate)

    if html_s:
        return write_article_from_html(
            vault_path,
            html_s,
            base_url=url_s,
            title=title,
            authors=authors,
            tags=tags,
            download_images=download_images,
            on_duplicate=on_duplicate,
            client=client,
            source_type=source_type,
            visibility=visibility,
            status=status,
        )

    assert url_s is not None
    return write_article_from_url(
        vault_path,
        url_s,
        title=title,
        authors=authors,
        tags=tags,
        download_images=download_images,
        on_duplicate=on_duplicate,
        client=client,
        visibility=visibility,
        status=status,
    )


def find_by_source_url(
    vault_path: str | Path,
    source_url: str,
    *,
    source_type: LibraryType | None = "article",
) -> Path | None:
    """Find an existing Library note whose frontmatter source_url matches."""
    vault = Path(vault_path).expanduser()
    target = _normalize_url(source_url)
    if not target:
        return None

    folders: list[Path] = []
    if source_type:
        folders.append(vault / LIBRARY_ROOT / FOLDER_BY_TYPE[source_type])
    else:
        for name in FOLDER_BY_TYPE.values():
            folders.append(vault / LIBRARY_ROOT / name)

    for folder in folders:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            meta, _ = _split_frontmatter(text)
            url = meta.get("source_url")
            if isinstance(url, str) and _normalize_url(url) == target:
                return path
    return None


def render_library_note(item: LibraryItem) -> str:
    """Render PRODUCT_v1 §7.2 note markdown."""
    title = (item.title or "Untitled").strip() or "Untitled"
    captured = item.captured_at or _now_iso()
    authors = [a.strip() for a in item.authors if (a or "").strip()]
    tags = [t.strip() for t in item.tags if (t or "").strip()]

    meta: dict[str, Any] = {
        "id": item.item_id or new_id("lib"),
        "title": title,
        "type": item.source_type,
        "source_url": item.canonical_url or "",
        "authors": authors,
        "captured_at": captured,
        "tags": tags,
        "visibility": item.visibility or "private",
        "status": item.status or "inbox",
    }
    if item.published_at:
        meta["published_at"] = item.published_at
    for key, value in (item.extra_frontmatter or {}).items():
        if key not in meta:
            meta[key] = value

    front = yaml.safe_dump(
        meta,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).strip()

    body = _strip_leading_h1(item.body_md or "", title).strip()
    highlights = list(item.highlights or [])
    notes = (item.notes_md or "").strip()

    parts = [
        "---",
        front,
        "---",
        "",
        f"# {title}",
        "",
    ]
    if body:
        parts.append(body)
        parts.append("")
    parts.extend(["## Highlights", ""])
    if highlights:
        for h in highlights:
            parts.append(f"- {h.strip()}" if not str(h).strip().startswith("- ") else str(h).strip())
        parts.append("")
    else:
        parts.extend(["- ", ""])
    parts.extend(["## Notes", ""])
    if notes:
        parts.append(notes)
        parts.append("")
    else:
        parts.append("")
    return "\n".join(parts)


def _unique_note_path(folder: Path, title: str) -> Path:
    stem = _natural_stem(title)
    candidate = folder / f"{stem}.md"
    if not candidate.exists():
        return candidate
    for i in range(2, 200):
        alt = folder / f"{stem} ({i}).md"
        if not alt.exists():
            return alt
    return folder / f"{stem} ({new_id()}).md"


def _natural_stem(title: str) -> str:
    cleaned = (title or "Untitled").strip()
    cleaned = cleaned.replace("/", "-").replace("\\", "-")
    for ch in ':*?"<>|':
        cleaned = cleaned.replace(ch, "")
    cleaned = " ".join(cleaned.split())
    return (cleaned or "Untitled")[:120]


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = _FRONTMATTER_RE.match(text or "")
    if not m:
        return {}, text or ""
    try:
        meta = yaml.safe_load(m.group(1)) or {}
        if not isinstance(meta, dict):
            meta = {}
    except yaml.YAMLError:
        meta = {}
    return meta, m.group(2)


def _section_body(markdown: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(markdown or "")
    return m.group(1) if m else ""


def _bullets_to_list(section: str) -> list[str]:
    items: list[str] = []
    for line in (section or "").splitlines():
        s = line.strip()
        if s.startswith("- "):
            value = s[2:].strip()
            if value and value != "…":
                items.append(value)
    return items


def _strip_leading_h1(body_md: str, title: str) -> str:
    text = (body_md or "").lstrip()
    if not text:
        return ""
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        heading = lines[0][2:].strip()
        if heading == title.strip() or not title.strip():
            return "\n".join(lines[1:]).lstrip("\n")
    return text


def _normalize_url(url: str) -> str:
    try:
        parsed = urlparse((url or "").strip())
    except Exception:  # noqa: BLE001
        return (url or "").strip().rstrip("/")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return (url or "").strip().rstrip("/")
    path = parsed.path.rstrip("/") or ""
    # Drop fragment; keep query (some CMS pages need it)
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}" + (
        f"?{parsed.query}" if parsed.query else ""
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
