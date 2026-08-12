"""Thinking Vault sync engine: Adapter → Normalizer → Writer (idempotent)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ...db import ThinkingSyncState, utcnow
from ...utils import workspace_config_dict
from .adapter import NotionThinkingAdapter
from .model import ThinkingObject
from .notion_client import NotionAPIError, NotionClient
from .writer import WriteResult, archive_thinking_note, thinking_vault_cfg, write_thinking_note

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    renamed: int = 0
    unchanged: int = 0
    archived: int = 0
    errors: list[str] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "renamed": self.renamed,
            "unchanged": self.unchanged,
            "archived": self.archived,
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


def apply_thinking_objects(
    db: Session,
    objects: list[ThinkingObject],
    *,
    vault_path: str,
    soft_archive_missing: bool = True,
    cfg: dict | None = None,
) -> SyncResult:
    """Write Thinking objects to the vault and update sync state.

    Same-batch title index should already be applied inside objects' connections.
    """
    cfg = cfg or workspace_config_dict()
    result = SyncResult()
    seen_ids: set[str] = set()

    for obj in objects:
        seen_ids.add(obj.source_id)
        state = _get_state(db, obj.source_id)
        prev_path = state.vault_path if state and state.status == "active" else None
        prev_hash = state.content_hash if state else None
        try:
            write = write_thinking_note(
                vault_path,
                obj,
                previous_relpath=prev_path,
                previous_hash=prev_hash,
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
            try:
                archived = archive_thinking_note(
                    vault_path,
                    previous_relpath=row.vault_path,
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
    cfg = workspace_config_dict()
    tv = thinking_vault_cfg(cfg)
    property_cfg = {
        "property_names": tv.get("property_names") or {},
    }
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
            cfg=cfg,
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
