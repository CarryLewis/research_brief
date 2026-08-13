"""Obsidian Writer — Canonical Thinking Object → Thinking notes / folders.

Identity is frontmatter ``source_id`` for notes, or ``.thinking-folder`` sidecar
for Status=folder directories. Filename / directory name follows the human title.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ...utils import content_hash, workspace_config_dict
from .model import PAGE_BODY_HEADING, SECTION_FIELDS, SECTION_HEADINGS, ThinkingObject

logger = logging.getLogger(__name__)

FOLDER_SIDECAR = ".thinking-folder"


@dataclass
class WriteResult:
    source_id: str
    vault_path: str
    action: str  # created | updated | unchanged | renamed | archived
    content_hash: str
    kind: str = "note"  # note | folder


def thinking_vault_cfg(cfg: dict | None = None) -> dict:
    cfg = cfg or workspace_config_dict()
    tv = dict(cfg.get("thinking_vault") or {})
    folders = cfg.get("folders") or {}
    tv.setdefault("folder", folders.get("thinking") or "Thinking")
    tv.setdefault(
        "archive_folder",
        str(Path(folders.get("archive") or "Archive") / "Thinking"),
    )
    return tv


def notes_root(vault: Path, cfg: dict | None = None) -> Path:
    tv = thinking_vault_cfg(cfg)
    folder = str(tv.get("folder") or "Thinking").strip() or "Thinking"
    if folder in {".", "./"}:
        return vault
    return vault / folder


def archive_root(vault: Path, cfg: dict | None = None) -> Path:
    tv = thinking_vault_cfg(cfg)
    return vault / str(tv.get("archive_folder") or "Archive/Thinking")


def natural_stem(title: str) -> str:
    """Human-readable filename / folder stem."""
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
    if "T" in raw:
        return raw.split("T", 1)[0]
    return raw[:10]


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def format_context_wikilinks(context: str) -> str:
    """Turn Context property into semicolon-joined Obsidian Wikilinks."""
    raw = (context or "").strip()
    if not raw:
        return ""
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


def read_note_source_id(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^source_id:\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


# Backward-compatible alias used inside this module.
_read_source_id = read_note_source_id


def read_folder_sidecar(folder: Path) -> dict | None:
    sidecar = folder / FOLDER_SIDECAR
    if not sidecar.is_file():
        return None
    try:
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


# Backward-compatible alias used inside this module.
_read_folder_sidecar = read_folder_sidecar


def _write_folder_sidecar(folder: Path, *, source_id: str, title: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"source_id": source_id, "title": title}
    text = yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)
    sidecar = folder / FOLDER_SIDECAR
    fd, tmp_name = tempfile.mkstemp(
        prefix=".tv_folder_", suffix=".yml", dir=str(folder)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, sidecar)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


def iter_thinking_notes(
    vault: Path,
    cfg: dict | None = None,
) -> list[Path]:
    """Recursively list Thinking markdown notes under notes + archive roots."""
    roots = [notes_root(vault, cfg), archive_root(vault, cfg)]
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            out.append(path)
    return out


def iter_thinking_folders(
    vault: Path,
    cfg: dict | None = None,
) -> list[Path]:
    """Find directories that carry a ``.thinking-folder`` sidecar."""
    roots = [notes_root(vault, cfg), archive_root(vault, cfg)]
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for sidecar in sorted(root.rglob(FOLDER_SIDECAR)):
            if sidecar.is_file():
                out.append(sidecar.parent)
    return out


def find_note_by_source_id(
    vault: Path,
    source_id: str,
    *,
    cfg: dict | None = None,
) -> Path | None:
    sid = (source_id or "").strip()
    if not sid:
        return None
    for path in iter_thinking_notes(vault, cfg):
        if _read_source_id(path) == sid:
            return path
    return None


def find_folder_by_source_id(
    vault: Path,
    source_id: str,
    *,
    cfg: dict | None = None,
) -> Path | None:
    sid = (source_id or "").strip()
    if not sid:
        return None
    for folder in iter_thinking_folders(vault, cfg):
        meta = _read_folder_sidecar(folder) or {}
        if str(meta.get("source_id") or "").strip() == sid:
            return folder
    return None


def _unique_child_dir(parent: Path, stem: str, source_id: str) -> Path:
    candidate = parent / stem
    if not candidate.exists():
        return candidate
    meta = _read_folder_sidecar(candidate) or {}
    existing = str(meta.get("source_id") or "").strip()
    if existing in {"", source_id}:
        return candidate
    short = source_id.replace("-", "")[-8:] or "folder"
    return parent / f"{stem} ({short})"


def resolve_folder_path(
    vault: Path,
    obj: ThinkingObject,
    *,
    parent_rel: str = "",
    previous_relpath: str | None = None,
    cfg: dict | None = None,
    archive: bool = False,
) -> tuple[Path, str]:
    """Choose destination directory for a folder ThinkingObject."""
    base = archive_root(vault, cfg) if archive else notes_root(vault, cfg)
    parent = base / parent_rel if parent_rel else base
    parent.mkdir(parents=True, exist_ok=True)
    stem = natural_stem(obj.title)
    candidate = _unique_child_dir(parent, stem, obj.source_id)

    if previous_relpath:
        known = vault / previous_relpath
        if known.is_dir():
            meta = _read_folder_sidecar(known) or {}
            if str(meta.get("source_id") or "").strip() == obj.source_id:
                if known.resolve() != candidate.resolve():
                    return candidate, "renamed"
                return known, "same"

    return candidate, "new"


def write_thinking_folder(
    vault_path: str | Path,
    obj: ThinkingObject,
    *,
    parent_rel: str = "",
    previous_relpath: str | None = None,
    previous_hash: str | None = None,
    cfg: dict | None = None,
    archive: bool = False,
) -> WriteResult:
    """Create / rename / soft-archive a real Obsidian directory (no index note)."""
    if not obj.source_id:
        raise ValueError("ThinkingObject.source_id is required")
    if not obj.is_folder():
        raise ValueError("write_thinking_folder requires Status=folder")

    vault = Path(vault_path).expanduser()
    digest = content_hash(obj.content_fingerprint())
    dest, path_kind = resolve_folder_path(
        vault,
        obj,
        parent_rel=parent_rel,
        previous_relpath=previous_relpath,
        cfg=cfg,
        archive=archive,
    )

    old_path: Path | None = None
    if previous_relpath:
        maybe_old = vault / previous_relpath
        if maybe_old.is_dir():
            meta = _read_folder_sidecar(maybe_old) or {}
            if str(meta.get("source_id") or "").strip() == obj.source_id:
                if maybe_old.resolve() != dest.resolve():
                    old_path = maybe_old

    if (
        previous_hash
        and previous_hash == digest
        and dest.is_dir()
        and (dest / FOLDER_SIDECAR).is_file()
        and old_path is None
    ):
        rel = str(dest.relative_to(vault))
        return WriteResult(
            source_id=obj.source_id,
            vault_path=rel,
            action="unchanged",
            content_hash=digest,
            kind="folder",
        )

    if old_path is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.resolve() != old_path.resolve():
            # Collision: move contents into candidate then remove old
            dest.mkdir(parents=True, exist_ok=True)
            for child in list(old_path.iterdir()):
                target = dest / child.name
                if target.exists():
                    continue
                shutil.move(str(child), str(target))
            shutil.rmtree(old_path, ignore_errors=True)
        else:
            shutil.move(str(old_path), str(dest))
        action = "archived" if archive else "renamed"
    else:
        dest.mkdir(parents=True, exist_ok=True)
        action = "archived" if archive else ("created" if path_kind == "new" else "updated")
        if previous_relpath or previous_hash:
            if action != "archived":
                action = "updated" if dest.exists() else "created"

    _write_folder_sidecar(dest, source_id=obj.source_id, title=obj.title)
    rel = str(dest.relative_to(vault))
    if archive:
        action = "archived"
    elif old_path is not None or path_kind == "renamed":
        action = "renamed"
    elif previous_hash or previous_relpath:
        # Sidecar rewrite / membership-only change
        if action == "created" and (vault / (previous_relpath or "")).exists():
            action = "updated"
        elif previous_hash == digest:
            action = "unchanged"
        elif action == "created" and previous_relpath:
            action = "updated"

    logger.info("Thinking folder %s → %s (%s)", obj.source_id, rel, action)
    return WriteResult(
        source_id=obj.source_id,
        vault_path=rel,
        action=action,
        content_hash=digest,
        kind="folder",
    )


def resolve_note_path(
    vault: Path,
    obj: ThinkingObject,
    *,
    previous_relpath: str | None = None,
    parent_rel: str = "",
    folder: str = "Thinking",
    cfg: dict | None = None,
) -> tuple[Path, str]:
    """Choose destination path; rename if title changed and previous file exists."""
    if cfg is not None or folder in {".", "./"} or parent_rel:
        base = notes_root(vault, cfg)
        out_dir = base / parent_rel if parent_rel else base
    else:
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
                    if candidate.exists() and _read_source_id(candidate) not in {
                        None,
                        obj.source_id,
                    }:
                        candidate = out_dir / f"{stem} ({obj.source_id[:8]}).md"
                    return candidate, "renamed"
                return known, "same"

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
    parent_rel: str = "",
    cfg: dict | None = None,
) -> WriteResult:
    """Write or update one Thinking markdown file. Idempotent by content hash."""
    if not obj.source_id:
        raise ValueError("ThinkingObject.source_id is required")
    if obj.is_folder():
        raise ValueError("Status=folder must use write_thinking_folder")

    vault = Path(vault_path).expanduser()
    tv = thinking_vault_cfg(cfg)
    folder = str(tv.get("folder") or "Thinking")
    markdown = render_markdown(obj)
    digest = content_hash(markdown)

    dest, path_kind = resolve_note_path(
        vault,
        obj,
        previous_relpath=previous_relpath,
        parent_rel=parent_rel,
        folder=folder,
        cfg=cfg,
    )

    if previous_hash and previous_hash == digest and dest.is_file():
        # Still need to move if parent folder changed
        if previous_relpath:
            known = vault / previous_relpath
            if known.is_file() and known.resolve() == dest.resolve():
                rel = str(dest.relative_to(vault))
                return WriteResult(
                    source_id=obj.source_id,
                    vault_path=rel,
                    action="unchanged",
                    content_hash=digest,
                    kind="note",
                )

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

    if action == "created" and previous_relpath:
        action = "updated"

    logger.info("Thinking note %s → %s (%s)", obj.source_id, rel, action)
    return WriteResult(
        source_id=obj.source_id,
        vault_path=rel,
        action=action,
        content_hash=digest,
        kind="note",
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
    dest_dir = archive_root(vault, cfg)
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


def archive_thinking_folder(
    vault_path: str | Path,
    *,
    previous_relpath: str,
    source_id: str,
    cfg: dict | None = None,
) -> str | None:
    """Soft-archive a Thinking folder directory under Archive/Thinking."""
    vault = Path(vault_path).expanduser()
    src = vault / previous_relpath
    if not src.is_dir():
        logger.warning(
            "Archive folder skip; missing dir %s for %s", previous_relpath, source_id
        )
        return None
    dest_dir = archive_root(vault, cfg)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        dest = dest_dir / f"{src.name} archived"
    try:
        shutil.move(str(src), str(dest))
    except OSError as exc:
        logger.error("Archive folder move failed %s → %s: %s", src, dest, exc)
        raise
    rel = str(dest.relative_to(vault))
    logger.info("Archived Thinking folder %s → %s", source_id, rel)
    return rel
