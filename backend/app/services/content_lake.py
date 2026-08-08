"""Immutable Content Lake — byte authority for the Knowledge OS.

Raw originals and media live here. Obsidian never stores these bytes.
"""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..connectors.base import MediaAsset
from ..db import ContentObject
from ..utils import new_id, sanitize_filename


@dataclass
class ContentObjectRef:
    id: str
    uri: str
    checksum: str
    mime: str
    byte_size: int
    filename: str | None
    role: str
    existed: bool = False


def lake_root() -> Path:
    return get_settings().content_lake_path


def bytes_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_path_for_checksum(checksum: str) -> Path:
    return lake_root() / "objects" / checksum[:2] / checksum


def uri_for_checksum(checksum: str) -> str:
    return f"lake://objects/{checksum[:2]}/{checksum}"


def open_uri(uri: str) -> Path:
    if not uri.startswith("lake://"):
        raise ValueError(f"Unsupported lake URI: {uri}")
    rel = uri[len("lake://") :]
    path = lake_root() / rel
    if not path.is_file():
        raise FileNotFoundError(uri)
    return path


def read_text(uri: str, encoding: str = "utf-8") -> str:
    return open_uri(uri).read_text(encoding=encoding)


def put_bytes(
    db: Session,
    data: bytes,
    *,
    mime: str = "application/octet-stream",
    role: str = "original",
    ko_id: str | None = None,
    filename: str | None = None,
    checksum: str | None = None,
) -> ContentObjectRef:
    """Write-once put. Identical checksum returns the existing object (never overwrite)."""
    if not data and role == "original":
        # Empty originals still get a stable checksum for indexing
        data = b""
    cs = checksum or bytes_checksum(data)
    uri = uri_for_checksum(cs)

    existing = (
        db.query(ContentObject)
        .filter((ContentObject.checksum == cs) | (ContentObject.uri == uri))
        .first()
    )
    if existing:
        if ko_id and not existing.ko_id:
            existing.ko_id = ko_id
            db.commit()
            db.refresh(existing)
        return ContentObjectRef(
            id=existing.id,
            uri=existing.uri,
            checksum=existing.checksum,
            mime=existing.mime,
            byte_size=existing.byte_size,
            filename=existing.filename,
            role=existing.role,
            existed=True,
        )

    target = object_path_for_checksum(cs)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(data)
    elif target.read_bytes() != data:
        # Collision on checksum should be cryptographically impossible; refuse overwrite
        raise ValueError(f"Content Lake checksum collision for {cs}")

    row = ContentObject(
        id=new_id("co"),
        ko_id=ko_id,
        role=role,
        uri=uri,
        checksum=cs,
        mime=mime or "application/octet-stream",
        byte_size=len(data),
        filename=filename,
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except Exception:
        # Concurrent/idempotent insert: another row may already own this uri
        db.rollback()
        existing = (
            db.query(ContentObject)
            .filter((ContentObject.checksum == cs) | (ContentObject.uri == uri))
            .first()
        )
        if not existing:
            raise
        if ko_id and not existing.ko_id:
            existing.ko_id = ko_id
            db.commit()
            db.refresh(existing)
        return ContentObjectRef(
            id=existing.id,
            uri=existing.uri,
            checksum=existing.checksum,
            mime=existing.mime,
            byte_size=existing.byte_size,
            filename=existing.filename,
            role=existing.role,
            existed=True,
        )
    return ContentObjectRef(
        id=row.id,
        uri=row.uri,
        checksum=row.checksum,
        mime=row.mime,
        byte_size=row.byte_size,
        filename=row.filename,
        role=row.role,
        existed=False,
    )


def put_text(
    db: Session,
    text: str,
    *,
    role: str = "original",
    ko_id: str | None = None,
    filename: str | None = None,
    mime: str = "text/plain; charset=utf-8",
) -> ContentObjectRef:
    return put_bytes(
        db,
        (text or "").encode("utf-8"),
        mime=mime,
        role=role,
        ko_id=ko_id,
        filename=filename,
    )


def put_file(
    db: Session,
    path: Path,
    *,
    role: str = "original",
    ko_id: str | None = None,
    mime: str | None = None,
) -> ContentObjectRef:
    data = path.read_bytes()
    guessed, _ = mimetypes.guess_type(str(path))
    return put_bytes(
        db,
        data,
        mime=mime or guessed or "application/octet-stream",
        role=role,
        ko_id=ko_id,
        filename=path.name,
    )


def store_media_asset(
    db: Session,
    asset: MediaAsset,
    *,
    ko_id: str | None = None,
    max_bytes: int = 40 * 1024 * 1024,
) -> ContentObjectRef | None:
    """Download remote media into the Content Lake (not Obsidian)."""
    try:
        headers = {"User-Agent": "ResearchBriefStudio/0.1 (+local; content-lake)"}
        with httpx.Client(timeout=60.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(asset.url)
            resp.raise_for_status()
            content = resp.content
            ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        if len(content) > max_bytes:
            return None
        if not ctype:
            ctype = mimetypes.guess_type(asset.url)[0] or "application/octet-stream"
        hint = asset.filename_hint or Path(urlparse(asset.url).path).name or "asset"
        filename = sanitize_filename(hint)
        return put_bytes(
            db,
            content,
            mime=ctype,
            role="media",
            ko_id=ko_id,
            filename=filename,
        )
    except Exception:  # noqa: BLE001
        return None
