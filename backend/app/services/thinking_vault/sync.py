"""Thinking Vault sync engine: Adapter → Normalizer → Writer (idempotent).

Two-phase write for Status=folder:
1. Create / rename real directories (and nest folders via Related Information)
2. Place ordinary notes under their owning folder (or notes root)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ...db import ThinkingSyncState, utcnow
from ...utils import content_hash
from .adapter import NotionThinkingAdapter
from .model import ThinkingObject
from .notion_client import NotionAPIError, NotionClient
from .writer import (
    WriteResult,
    archive_root,
    archive_thinking_folder,
    archive_thinking_note,
    iter_thinking_folders,
    iter_thinking_notes,
    notes_root,
    read_folder_sidecar,
    read_note_source_id,
    write_thinking_folder,
    write_thinking_note,
)

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    renamed: int = 0
    unchanged: int = 0
    archived: int = 0
    folders: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "renamed": self.renamed,
            "unchanged": self.unchanged,
            "archived": self.archived,
            "folders": self.folders,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "items": list(self.items),
        }


def _get_state(db: Session, source_id: str) -> ThinkingSyncState | None:
    return db.get(ThinkingSyncState, source_id)


def _upsert_state(
    db: Session,
    *,
    source_id: str,
    title: str,
    vault_path: str,
    content_hash_value: str,
    notion_last_edited: str,
    status: str,
) -> ThinkingSyncState:
    row = _get_state(db, source_id)
    if row is None:
        row = ThinkingSyncState(
            source_id=source_id,
            title=title,
            vault_path=vault_path,
            content_hash=content_hash_value,
            notion_last_edited=notion_last_edited,
            status=status,
            last_synced_at=utcnow(),
        )
        db.add(row)
    else:
        row.title = title
        row.vault_path = vault_path
        row.content_hash = content_hash_value
        row.notion_last_edited = notion_last_edited
        row.status = status
        row.last_synced_at = utcnow()
        row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def _norm_id(value: str) -> str:
    return (value or "").replace("-", "").strip().lower()


def _pick_lex_smallest(
    candidates: list[tuple[str, ThinkingObject]],
) -> ThinkingObject:
    """Pick owning folder by lexicographically smallest title, then source_id."""
    return sorted(candidates, key=lambda item: (item[1].title.casefold(), item[0]))[0][1]


def build_membership(
    folders: list[ThinkingObject],
    notes: list[ThinkingObject],
    *,
    warnings: list[str],
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Return (note_id→folder_id, child_folder_id→parent_folder_id, cycle_errors).

    Multi-membership: keep the folder with the lexicographically smallest title.
    """
    folder_by_id: dict[str, ThinkingObject] = {f.source_id: f for f in folders}
    folder_by_norm: dict[str, ThinkingObject] = {
        _norm_id(f.source_id): f for f in folders
    }
    note_ids = {n.source_id for n in notes}
    note_norms = {_norm_id(n.source_id): n.source_id for n in notes}

    note_claims: dict[str, list[tuple[str, ThinkingObject]]] = {}
    folder_claims: dict[str, list[tuple[str, ThinkingObject]]] = {}

    for folder in folders:
        for conn in folder.connections:
            cid = (conn.source_id or "").strip()
            if not cid:
                continue
            target_folder = folder_by_id.get(cid) or folder_by_norm.get(_norm_id(cid))
            if target_folder is not None:
                if target_folder.source_id == folder.source_id:
                    continue
                folder_claims.setdefault(target_folder.source_id, []).append(
                    (folder.source_id, folder)
                )
                continue
            note_id = cid if cid in note_ids else note_norms.get(_norm_id(cid))
            if note_id:
                note_claims.setdefault(note_id, []).append((folder.source_id, folder))

    note_owner: dict[str, str] = {}
    for note_id, claims in note_claims.items():
        unique: dict[str, ThinkingObject] = {fid: obj for fid, obj in claims}
        if len(unique) > 1:
            titles = ", ".join(sorted(o.title for o in unique.values()))
            warnings.append(
                f"note {note_id} claimed by multiple folders ({titles}); "
                "using lexicographically smallest title"
            )
        owner = _pick_lex_smallest(list(unique.items()))
        note_owner[note_id] = owner.source_id

    parent_of: dict[str, str] = {}
    for child_id, claims in folder_claims.items():
        unique: dict[str, ThinkingObject] = {fid: obj for fid, obj in claims}
        if len(unique) > 1:
            titles = ", ".join(sorted(o.title for o in unique.values()))
            warnings.append(
                f"folder {child_id} claimed by multiple parents ({titles}); "
                "using lexicographically smallest title"
            )
        owner = _pick_lex_smallest(list(unique.items()))
        parent_of[child_id] = owner.source_id

    # Drop edges that create cycles.
    cycle_errors: list[str] = []
    cleaned: dict[str, str] = {}
    for child, parent in parent_of.items():
        seen = {child}
        cur = parent
        cyclic = False
        while cur:
            if cur in seen:
                cyclic = True
                break
            seen.add(cur)
            cur = parent_of.get(cur, "")
        if cyclic:
            cycle_errors.append(
                f"folder nesting cycle involving {child}; nesting edge skipped"
            )
            continue
        cleaned[child] = parent

    return note_owner, cleaned, cycle_errors


def _folder_parent_rel(
    folder_id: str,
    *,
    parent_of: dict[str, str],
    folder_paths: dict[str, str],
    notes_base: Path,
    vault: Path,
) -> str:
    parent_id = parent_of.get(folder_id)
    if not parent_id:
        return ""
    parent_path = folder_paths.get(parent_id)
    if not parent_path:
        return ""
    abs_parent = vault / parent_path
    try:
        return str(abs_parent.relative_to(notes_base))
    except ValueError:
        return ""


def _note_parent_rel(
    note_id: str,
    *,
    note_owner: dict[str, str],
    folder_paths: dict[str, str],
    notes_base: Path,
    vault: Path,
) -> str:
    folder_id = note_owner.get(note_id)
    if not folder_id:
        return ""
    folder_path = folder_paths.get(folder_id)
    if not folder_path:
        return ""
    abs_folder = vault / folder_path
    try:
        return str(abs_folder.relative_to(notes_base))
    except ValueError:
        return ""


def _topo_folder_order(
    folders: list[ThinkingObject],
    parent_of: dict[str, str],
) -> list[ThinkingObject]:
    """Parents before children."""
    by_id = {f.source_id: f for f in folders}
    remaining = set(by_id)
    ordered: list[ThinkingObject] = []
    while remaining:
        progressed = False
        for fid in sorted(remaining, key=lambda i: by_id[i].title.casefold()):
            parent = parent_of.get(fid)
            if parent and parent in remaining:
                continue
            ordered.append(by_id[fid])
            remaining.remove(fid)
            progressed = True
        if not progressed:
            # Cycle residue — append remaining stably
            for fid in sorted(remaining, key=lambda i: by_id[i].title.casefold()):
                ordered.append(by_id[fid])
            break
    return ordered


def hydrate_sync_state_from_vault(
    db: Session,
    vault_path: str | Path,
    *,
    cfg: dict | None = None,
) -> int:
    """Seed missing ThinkingSyncState rows from on-disk notes/folders.

    Needed for GitHub Actions (ephemeral SQLite) so renames and soft-archive
    still work across workflow runs when the DB cache is cold.
    """
    vault = Path(vault_path).expanduser()
    cfg = cfg or {}
    archive = archive_root(vault, cfg)
    seeded = 0

    for path in iter_thinking_notes(vault, cfg):
        source_id = read_note_source_id(path)
        if not source_id or _get_state(db, source_id) is not None:
            continue
        try:
            rel = str(path.relative_to(vault))
        except ValueError:
            continue
        try:
            digest = content_hash(path.read_text(encoding="utf-8"))
        except OSError:
            digest = ""
        under_archive = archive in path.parents or path.parent == archive
        _upsert_state(
            db,
            source_id=source_id,
            title=path.stem,
            vault_path=rel,
            content_hash_value=digest,
            notion_last_edited="",
            status="archived" if under_archive else "active",
        )
        seeded += 1

    for folder in iter_thinking_folders(vault, cfg):
        meta = read_folder_sidecar(folder) or {}
        source_id = str(meta.get("source_id") or "").strip()
        if not source_id or _get_state(db, source_id) is not None:
            continue
        try:
            rel = str(folder.relative_to(vault))
        except ValueError:
            continue
        under_archive = archive in folder.parents or folder.parent == archive
        title = str(meta.get("title") or folder.name).strip() or folder.name
        _upsert_state(
            db,
            source_id=source_id,
            title=title,
            vault_path=rel,
            content_hash_value="",
            notion_last_edited="",
            status="archived" if under_archive else "active",
        )
        seeded += 1

    if seeded:
        logger.info("Hydrated %s ThinkingSyncState rows from vault", seeded)
    return seeded


def apply_thinking_objects(
    db: Session,
    objects: list[ThinkingObject],
    *,
    vault_path: str,
    soft_archive_missing: bool = True,
    cfg: dict | None = None,
) -> SyncResult:
    """Write Thinking objects to the vault and update sync state."""
    cfg = cfg or {}
    result = SyncResult()
    vault = Path(vault_path).expanduser()
    notes_base = notes_root(vault, cfg)
    hydrate_sync_state_from_vault(db, vault, cfg=cfg)

    folders = [o for o in objects if o.is_folder() and o.source_id]
    notes = [o for o in objects if not o.is_folder() and o.source_id]
    seen_ids: set[str] = {o.source_id for o in objects if o.source_id}

    note_owner, parent_of, cycle_errors = build_membership(
        folders, notes, warnings=result.warnings
    )
    result.errors.extend(cycle_errors)

    folder_paths: dict[str, str] = {}
    for obj in _topo_folder_order(folders, parent_of):
        state = _get_state(db, obj.source_id)
        prev_path = state.vault_path if state and state.status == "active" else None
        prev_hash = state.content_hash if state else None
        parent_rel = _folder_parent_rel(
            obj.source_id,
            parent_of=parent_of,
            folder_paths=folder_paths,
            notes_base=notes_base,
            vault=vault,
        )
        try:
            write = write_thinking_folder(
                vault_path,
                obj,
                parent_rel=parent_rel,
                previous_relpath=prev_path,
                previous_hash=prev_hash,
                cfg=cfg,
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"folder write failed for {obj.source_id}: {exc}"
            logger.error(msg)
            result.errors.append(msg)
            continue

        folder_paths[obj.source_id] = write.vault_path
        _upsert_state(
            db,
            source_id=obj.source_id,
            title=obj.title,
            vault_path=write.vault_path,
            content_hash_value=write.content_hash,
            notion_last_edited=obj.updated_at,
            status="active",
        )
        _count_action(result, write)
        result.folders += 1
        result.items.append(
            {
                "source_id": obj.source_id,
                "title": obj.title,
                "vault_path": write.vault_path,
                "action": write.action,
                "kind": "folder",
            }
        )

    for obj in notes:
        state = _get_state(db, obj.source_id)
        prev_path = state.vault_path if state and state.status == "active" else None
        prev_hash = state.content_hash if state else None
        parent_rel = _note_parent_rel(
            obj.source_id,
            note_owner=note_owner,
            folder_paths=folder_paths,
            notes_base=notes_base,
            vault=vault,
        )
        try:
            write = write_thinking_note(
                vault_path,
                obj,
                previous_relpath=prev_path,
                previous_hash=prev_hash,
                parent_rel=parent_rel,
                cfg=cfg,
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"write failed for {obj.source_id}: {exc}"
            logger.error(msg)
            result.errors.append(msg)
            continue

        _upsert_state(
            db,
            source_id=obj.source_id,
            title=obj.title,
            vault_path=write.vault_path,
            content_hash_value=write.content_hash,
            notion_last_edited=obj.updated_at,
            status="active",
        )
        _count_action(result, write)
        result.items.append(
            {
                "source_id": obj.source_id,
                "title": obj.title,
                "vault_path": write.vault_path,
                "action": write.action,
                "kind": "note",
            }
        )

    if soft_archive_missing:
        active_rows = (
            db.query(ThinkingSyncState)
            .filter(ThinkingSyncState.status == "active")
            .all()
        )
        for row in active_rows:
            if row.source_id in seen_ids:
                continue
            prev = row.vault_path or ""
            abs_prev = vault / prev if prev else None
            try:
                if abs_prev and abs_prev.is_dir():
                    archived = archive_thinking_folder(
                        vault_path,
                        previous_relpath=prev,
                        source_id=row.source_id,
                        cfg=cfg,
                    )
                else:
                    archived = archive_thinking_note(
                        vault_path,
                        previous_relpath=prev,
                        source_id=row.source_id,
                        cfg=cfg,
                    )
            except Exception as exc:  # noqa: BLE001
                msg = f"archive failed for {row.source_id}: {exc}"
                logger.error(msg)
                result.errors.append(msg)
                continue
            row.status = "archived"
            if archived:
                row.vault_path = archived
            row.last_synced_at = utcnow()
            row.updated_at = utcnow()
            db.commit()
            result.archived += 1
            result.items.append(
                {
                    "source_id": row.source_id,
                    "title": row.title,
                    "vault_path": row.vault_path,
                    "action": "archived",
                }
            )

    return result


def _count_action(result: SyncResult, write: WriteResult) -> None:
    if write.action == "created":
        result.created += 1
    elif write.action == "updated":
        result.updated += 1
    elif write.action == "renamed":
        result.renamed += 1
    elif write.action == "archived":
        result.archived += 1
    else:
        result.unchanged += 1


def sync_from_notion(
    db: Session,
    *,
    vault_path: str,
    token: str,
    database_id: str,
    client: NotionClient | None = None,
    soft_archive_missing: bool = True,
) -> SyncResult:
    """Full Notion → Obsidian Thinking sync."""
    property_cfg: dict[str, Any] = {}
    owns = client is None
    notion = client or NotionClient(token)
    try:
        adapter = NotionThinkingAdapter(
            notion,
            database_id,
            property_cfg=property_cfg,
        )
        objects = adapter.fetch_thinking_objects()
        # Second pass: refresh connection titles from this batch's titles
        title_index = {o.source_id: o.title for o in objects}
        title_index.update({o.source_id.replace("-", ""): o.title for o in objects})
        for obj in objects:
            for conn in obj.connections:
                if conn.source_id:
                    resolved = title_index.get(conn.source_id) or title_index.get(
                        conn.source_id.replace("-", "")
                    )
                    if resolved:
                        conn.title = resolved
        return apply_thinking_objects(
            db,
            objects,
            vault_path=vault_path,
            soft_archive_missing=soft_archive_missing,
        )
    except NotionAPIError as exc:
        logger.error("Thinking sync Notion failure: %s", exc)
        result = SyncResult()
        result.errors.append(str(exc))
        return result
    finally:
        if owns:
            notion.close()


def last_sync_status(db: Session) -> dict[str, Any]:
    rows = db.query(ThinkingSyncState).order_by(ThinkingSyncState.updated_at.desc()).all()
    active = sum(1 for r in rows if r.status == "active")
    archived = sum(1 for r in rows if r.status == "archived")
    latest = rows[0].last_synced_at.isoformat() if rows and rows[0].last_synced_at else None
    return {
        "active": active,
        "archived": archived,
        "total": len(rows),
        "last_synced_at": latest,
    }
