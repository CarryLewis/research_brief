"""Obsidian Writer — Canonical Thinking Object → Thinking/*.md."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ...utils import content_hash, workspace_config_dict
from .model import PAGE_BODY_HEADING, SECTION_FIELDS, SECTION_HEADINGS, ThinkingObject

logger = logging.getLogger(__name__)


@dataclass
class WriteResult:
    source_id: str
    vault_path: str
    action: str  # created | updated | unchanged | renamed
    content_hash: str


def thinking_vault_cfg(cfg: dict | None = None) -> dict:
    cfg = cfg or workspace_config_dict()
    tv = dict(cfg.get("thinking_vault") or {})
    folders = cfg.get("folders") or {}
    tv.setdefault("folder", folders.get("thinking") or "Thinking")
    tv.setdefault(
        "archive_folder",
        str(Path(folders.get("archive") or "Archive") / "Thinking"),
    )
    info_root = folders.get("information") or "Information"
    tv.setdefault("information_folder", info_root)
    tv.setdefault("information_books", str(Path(info_root) / "Books"))
    tv.setdefault("information_articles", str(Path(info_root) / "Articles"))
    return tv


def natural_stem(title: str) -> str:
    """Human-readable filename stem (shared rules with workspace)._natural_stem."""
    cleaned = (title or "Untitled").strip()
    cleaned = cleaned.replace("/", "-").replace("\\", "-")
    for ch in ':*?"<>|':
        cleaned = cleaned.replace(ch, "")
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        cleaned = "Untitled"
    return cleaned[:120]


def _date_only(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Notion ISO → YYYY-MM-DD
    if "T" in raw:
        return raw.split("T", 1)[0]
    return raw[:10]


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def format_context_wikilinks(context: str) -> str:
    """Turn Context property into semicolon-joined Obsidian Wikilinks.

    Input terms are split on ``;`` (full-width ``；`` also accepted).
    Existing ``[[...]]`` wrappers are preserved.
    """
    raw = (context or "").strip()
    if not raw:
        return ""
    # Prefer Chinese semicolon, also allow ASCII
    normalized = raw.replace("；", ";")
    parts: list[str] = []
    seen: set[str] = set()
    for chunk in normalized.split(";"):
        term = chunk.strip()
        if not term:
            continue
        if term.startswith("[[") and term.endswith("]]"):
            inner = term[2:-2].strip()
        else:
            inner = term.strip("[]").strip()
        if not inner:
            continue
        key = inner.casefold()
        if key in seen:
            continue
        seen.add(key)
        parts.append(f"[[{inner}]]")
    return "; ".join(parts)


def render_markdown(obj: ThinkingObject) -> str:
    """Render minimal frontmatter + non-empty sections + page body + Connections."""
    lines = [
        "---",
        "source: notion",
        f'source_id: "{_yaml_escape(obj.source_id)}"',
        f"created: {_date_only(obj.created_at)}",
        f"updated: {_date_only(obj.updated_at)}",
        "---",
        "",
        f"# {obj.title}",
    ]
    for field_name in SECTION_FIELDS:
        body = (getattr(obj, field_name) or "").strip()
        if not body:
            continue
        heading = SECTION_HEADINGS[field_name]
        if field_name == "context":
            body = format_context_wikilinks(body)
            if not body:
                continue
        lines.extend(["", f"## {heading}", "", body])

    page_body = (obj.page_body or "").strip()
    if page_body:
        lines.extend(["", f"## {PAGE_BODY_HEADING}", "", page_body])

    if obj.connections:
        lines.extend(["", "## Connections", ""])
        seen: set[str] = set()
        for conn in obj.connections:
            title = conn.title.strip()
            if not title or title in seen:
                continue
            seen.add(title)
            lines.append(f"[[{title}]]")

    # Controlled filter tags → Obsidian #tags at page bottom (not a ## section).
    footer_tags = [t.strip() for t in (obj.tags or []) if str(t or "").strip()]
    if footer_tags:
        lines.extend(["", " ".join(f"#{t}" for t in footer_tags)])

    lines.append("")
    return "\n".join(lines)


def render_information_markdown(obj: ThinkingObject) -> str:
    """Render book/article notes under Information/ (not Thinking sections)."""
    page_type = obj.page_type if obj.is_information() else "article"
    lines = [
        "---",
        "source: notion",
        f'source_id: "{_yaml_escape(obj.source_id)}"',
        f"type: {page_type}",
        f"created: {_date_only(obj.created_at)}",
        f"updated: {_date_only(obj.updated_at)}",
    ]
    if obj.source_url:
        lines.append(f'url: "{_yaml_escape(obj.source_url)}"')
    if obj.tags:
        lines.append("tags:")
        for tag in obj.tags:
            lines.append(f"  - {tag}")
    lines.extend(["---", "", f"# {obj.title}"])

    body = (obj.page_body or "").strip() or (obj.raw_thought or "").strip()
    if body:
        lines.extend(["", "## Body", "", body])

    if obj.connections:
        lines.extend(["", "## Connections", ""])
        seen: set[str] = set()
        for conn in obj.connections:
            title = conn.title.strip()
            if not title or title in seen:
                continue
            seen.add(title)
            lines.append(f"[[{title}]]")

    footer_tags = [t.strip() for t in (obj.tags or []) if str(t or "").strip()]
    if footer_tags:
        lines.extend(["", " ".join(f"#{t}" for t in footer_tags)])

    lines.append("")
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tv_", suffix=".md", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


def _read_source_id(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^source_id:\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def resolve_note_path(
    vault: Path,
    obj: ThinkingObject,
    *,
    previous_relpath: str | None = None,
    folder: str = "Thinking",
) -> tuple[Path, str]:
    """Choose destination path; rename if title changed and previous file exists."""
    out_dir = vault / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = natural_stem(obj.title)
    candidate = out_dir / f"{stem}.md"

    if previous_relpath:
        known = vault / previous_relpath
        if known.is_file():
            known_id = _read_source_id(known)
            if known_id == obj.source_id:
                if known.resolve() != candidate.resolve():
                    # Title rename: move to new name; disambiguate collisions
                    if candidate.exists() and _read_source_id(candidate) not in {
                        None,
                        obj.source_id,
                    }:
                        candidate = out_dir / f"{stem} ({obj.source_id[:8]}).md"
                    return candidate, "renamed"
                return known, "same"
            # Stale path — fall through

    if candidate.exists():
        existing_id = _read_source_id(candidate)
        if existing_id and existing_id != obj.source_id:
            candidate = out_dir / f"{stem} ({obj.source_id[:8]}).md"

    return candidate, "new"


def write_thinking_note(
    vault_path: str | Path,
    obj: ThinkingObject,
    *,
    previous_relpath: str | None = None,
    previous_hash: str | None = None,
    cfg: dict | None = None,
    target_folder: str | None = None,
) -> WriteResult:
    """Write or update one Thinking markdown file. Idempotent by content hash."""
    if not obj.source_id:
        raise ValueError("ThinkingObject.source_id is required")

    vault = Path(vault_path).expanduser()
    tv = thinking_vault_cfg(cfg)
    folder = (target_folder or "").strip() or str(tv.get("folder") or "Thinking")
    markdown = render_markdown(obj)
    digest = content_hash(markdown)

    dest, path_kind = resolve_note_path(
        vault,
        obj,
        previous_relpath=previous_relpath,
        folder=folder,
    )

    if previous_hash and previous_hash == digest and dest.is_file():
        rel = str(dest.relative_to(vault))
        return WriteResult(
            source_id=obj.source_id,
            vault_path=rel,
            action="unchanged",
            content_hash=digest,
        )

    # Rename: write new then remove old if different path
    old_path: Path | None = None
    if previous_relpath:
        maybe_old = vault / previous_relpath
        if maybe_old.is_file() and maybe_old.resolve() != dest.resolve():
            if _read_source_id(maybe_old) == obj.source_id:
                old_path = maybe_old

    try:
        _atomic_write(dest, markdown)
    except OSError as exc:
        logger.error("Filesystem write failed for %s: %s", dest, exc)
        raise

    if old_path is not None and old_path.exists():
        try:
            old_path.unlink()
        except OSError as exc:
            logger.warning("Could not remove old Thinking file %s: %s", old_path, exc)

    rel = str(dest.relative_to(vault))
    if path_kind == "renamed" or (old_path is not None):
        action = "renamed"
    elif previous_relpath and (vault / previous_relpath).exists() is False and previous_hash:
        action = "updated"
    elif previous_hash or previous_relpath:
        action = "updated"
    else:
        action = "created"

    # Refine: if file existed at dest already with same source_id → updated
    if action == "created" and previous_relpath:
        action = "updated"

    logger.info("Thinking note %s → %s (%s)", obj.source_id, rel, action)
    return WriteResult(
        source_id=obj.source_id,
        vault_path=rel,
        action=action,
        content_hash=digest,
    )


def write_information_note(
    vault_path: str | Path,
    obj: ThinkingObject,
    *,
    previous_relpath: str | None = None,
    previous_hash: str | None = None,
    cfg: dict | None = None,
) -> WriteResult:
    """Write book/article markdown under Information/Books|Articles."""
    if not obj.source_id:
        raise ValueError("ThinkingObject.source_id is required")

    vault = Path(vault_path).expanduser()
    tv = thinking_vault_cfg(cfg)
    if obj.page_type == "book":
        folder = str(tv.get("information_books") or "Information/Books")
    else:
        folder = str(tv.get("information_articles") or "Information/Articles")

    markdown = render_information_markdown(obj)
    digest = content_hash(markdown)
    dest, path_kind = resolve_note_path(
        vault,
        obj,
        previous_relpath=previous_relpath,
        folder=folder,
    )

    if previous_hash and previous_hash == digest and dest.is_file():
        rel = str(dest.relative_to(vault))
        return WriteResult(
            source_id=obj.source_id,
            vault_path=rel,
            action="unchanged",
            content_hash=digest,
        )

    old_path: Path | None = None
    if previous_relpath:
        maybe_old = vault / previous_relpath
        if maybe_old.is_file() and maybe_old.resolve() != dest.resolve():
            if _read_source_id(maybe_old) == obj.source_id:
                old_path = maybe_old

    _atomic_write(dest, markdown)
    if old_path is not None and old_path.exists():
        try:
            old_path.unlink()
        except OSError as exc:
            logger.warning("Could not remove old Information file %s: %s", old_path, exc)

    rel = str(dest.relative_to(vault))
    if path_kind == "renamed" or (old_path is not None):
        action = "renamed"
    elif previous_hash or previous_relpath:
        action = "updated"
    else:
        action = "created"
    if action == "created" and previous_relpath:
        action = "updated"

    logger.info("Information note %s → %s (%s)", obj.source_id, rel, action)
    return WriteResult(
        source_id=obj.source_id,
        vault_path=rel,
        action=action,
        content_hash=digest,
    )


def write_folder_directory(
    vault_path: str | Path,
    obj: ThinkingObject,
    *,
    folder_dir: str,
    previous_relpath: str | None = None,
    previous_hash: str | None = None,
) -> WriteResult:
    """Ensure a real Obsidian directory exists for a Type=folder page (no .md)."""
    if not obj.source_id:
        raise ValueError("ThinkingObject.source_id is required")
    vault = Path(vault_path).expanduser()
    rel = (folder_dir or "").strip().strip("/")
    if not rel:
        raise ValueError("folder_dir is required")
    digest = content_hash(f"folder:{rel}:{obj.title}:{obj.source_id}")
    dest = vault / rel
    existed = dest.is_dir()
    dest.mkdir(parents=True, exist_ok=True)
    keep = dest / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")

    if previous_hash == digest and existed:
        action = "unchanged"
    elif previous_relpath:
        action = "updated"
    else:
        action = "created"

    logger.info("Folder dir %s → %s (%s)", obj.source_id, rel, action)
    return WriteResult(
        source_id=obj.source_id,
        vault_path=rel,
        action=action,
        content_hash=digest,
    )


def write_vault_object(
    vault_path: str | Path,
    obj: ThinkingObject,
    *,
    previous_relpath: str | None = None,
    previous_hash: str | None = None,
    cfg: dict | None = None,
    target_folder: str | None = None,
    folder_dir: str | None = None,
) -> WriteResult:
    """Dispatch write by page Type."""
    if obj.is_folder():
        if not folder_dir:
            tv = thinking_vault_cfg(cfg)
            folder_dir = str(Path(tv.get("folder") or "Thinking") / natural_stem(obj.title))
        return write_folder_directory(
            vault_path,
            obj,
            folder_dir=folder_dir,
            previous_relpath=previous_relpath,
            previous_hash=previous_hash,
        )
    if obj.is_information():
        return write_information_note(
            vault_path,
            obj,
            previous_relpath=previous_relpath,
            previous_hash=previous_hash,
            cfg=cfg,
        )
    return write_thinking_note(
        vault_path,
        obj,
        previous_relpath=previous_relpath,
        previous_hash=previous_hash,
        cfg=cfg,
        target_folder=target_folder,
    )


def archive_thinking_note(
    vault_path: str | Path,
    *,
    previous_relpath: str,
    source_id: str,
    cfg: dict | None = None,
) -> str | None:
    """Soft-archive a Thinking note under Archive/Thinking (no hard delete)."""
    vault = Path(vault_path).expanduser()
    src = vault / previous_relpath
    if not src.is_file():
        logger.warning("Archive skip; missing file %s for %s", previous_relpath, source_id)
        return None
    tv = thinking_vault_cfg(cfg)
    archive_folder = str(tv.get("archive_folder") or "Archive/Thinking")
    dest_dir = vault / archive_folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        dest = dest_dir / f"{src.stem} archived{src.suffix}"
    try:
        src.replace(dest)
    except OSError as exc:
        logger.error("Archive move failed %s → %s: %s", src, dest, exc)
        raise
    rel = str(dest.relative_to(vault))
    logger.info("Archived Thinking note %s → %s", source_id, rel)
    return rel
