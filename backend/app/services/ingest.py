from __future__ import annotations

from sqlalchemy.orm import Session

from ..connectors import CONNECTORS
from ..connectors.base import FetchedDoc
from ..connectors.manual import ManualConnector
from ..db import SourceDoc
from ..schemas import ManualImportIn, SourceOut
from ..utils import content_hash, dumps, excerpt, loads, new_id
from . import knowledge as knowledge_svc


def source_to_out(src: SourceDoc) -> SourceOut:
    return SourceOut(
        id=src.id,
        notebook_id=src.notebook_id,
        connector=src.connector,
        title=src.title,
        url=src.url,
        authors=src.authors,
        published_at=src.published_at,
        raw_text=src.raw_text,
        content_hash=src.content_hash,
        status=src.status,
        error=src.error,
        metadata=loads(src.metadata_json, {}),
        created_at=src.created_at,
        excerpt=excerpt(src.raw_text),
    )


def _existing_hashes(db: Session, notebook_id: str) -> set[str]:
    rows = db.query(SourceDoc.content_hash).filter(SourceDoc.notebook_id == notebook_id).all()
    return {r[0] for r in rows}


def _existing_urls(db: Session, notebook_id: str) -> set[str]:
    rows = (
        db.query(SourceDoc.url)
        .filter(SourceDoc.notebook_id == notebook_id, SourceDoc.url.isnot(None))
        .all()
    )
    return {r[0] for r in rows if r[0]}


def persist_fetched(
    db: Session,
    notebook_id: str,
    docs: list[FetchedDoc],
    *,
    store_media: bool = True,
) -> tuple[list[SourceDoc], list[FetchedDoc], int, int]:
    """Persist docs; return (added_orm, added_fetched, skipped, failed)."""
    hashes = _existing_hashes(db, notebook_id)
    urls = _existing_urls(db, notebook_id)
    added_orm: list[SourceDoc] = []
    added_fetched: list[FetchedDoc] = []
    skipped = 0
    failed = 0
    for doc in docs:
        if doc.status == "failed":
            failed += 1
            src = SourceDoc(
                id=new_id("src"),
                notebook_id=notebook_id,
                connector=doc.connector,
                title=doc.title,
                url=doc.url,
                authors=doc.authors,
                published_at=doc.published_at,
                raw_text=doc.raw_text or "",
                content_hash=content_hash(doc.title + str(doc.error)),
                status="failed",
                error=doc.error,
                metadata_json=dumps(doc.metadata),
            )
            db.add(src)
            continue
        h = content_hash(doc.raw_text or doc.title)
        if h in hashes or (doc.url and doc.url in urls):
            skipped += 1
            continue
        meta = dict(doc.metadata or {})
        if doc.media:
            meta["media"] = [
                {"url": m.url, "kind": m.kind, "filename_hint": m.filename_hint}
                for m in doc.media
            ]
        src = SourceDoc(
            id=new_id("src"),
            notebook_id=notebook_id,
            connector=doc.connector,
            title=doc.title,
            url=doc.url,
            authors=doc.authors,
            published_at=doc.published_at,
            raw_text=doc.raw_text,
            content_hash=h,
            status="ready",
            metadata_json=dumps(meta),
        )
        db.add(src)
        hashes.add(h)
        if doc.url:
            urls.add(doc.url)
        added_orm.append(src)
        added_fetched.append(doc)
    db.commit()
    for s in added_orm:
        db.refresh(s)
        # Content Lake + Knowledge Object (canonical structured layer)
        knowledge_svc.upsert_from_source(
            db, s, store_lake=True, store_media=store_media
        )
    return added_orm, added_fetched, skipped, failed


def import_manual(db: Session, notebook_id: str, payload: ManualImportIn) -> SourceOut:
    connector = ManualConnector()
    doc = connector.from_payload(
        title=payload.title,
        text=payload.text,
        url=payload.url,
        authors=payload.authors,
        published_at=payload.published_at,
        metadata=payload.metadata,
    )
    added, _, _, _ = persist_fetched(db, notebook_id, [doc])
    if not added:
        h = content_hash(payload.text)
        existing = (
            db.query(SourceDoc)
            .filter(SourceDoc.notebook_id == notebook_id, SourceDoc.content_hash == h)
            .first()
        )
        if existing:
            return source_to_out(existing)
        raise ValueError("Import failed")
    return source_to_out(added[0])


def fetch_from_scope(
    scope: dict,
    connectors: list[str] | None = None,
    channel_ids: list[str] | None = None,
) -> list[FetchedDoc]:
    from .channels import resolve_ingest_plan

    effective = resolve_ingest_plan(scope, selected_channel_ids=channel_ids)
    if connectors:
        source_types = connectors
    else:
        source_types = effective.get("source_types") or list(CONNECTORS.keys())

    all_docs: list[FetchedDoc] = []
    for name in source_types:
        if name == "manual":
            continue
        connector = CONNECTORS.get(name)
        if not connector:
            continue
        try:
            all_docs.extend(connector.fetch(effective))
        except Exception as exc:  # noqa: BLE001
            all_docs.append(
                FetchedDoc(
                    connector=name,
                    title=f"{name} connector error",
                    raw_text="",
                    status="failed",
                    error=str(exc),
                )
            )
    return all_docs


def ingest_from_scope(
    db: Session,
    notebook_id: str,
    scope: dict,
    connectors: list[str] | None = None,
    channel_ids: list[str] | None = None,
    *,
    store_media: bool = True,
) -> tuple[list[SourceOut], list[FetchedDoc], int, int, int]:
    all_docs = fetch_from_scope(scope, connectors, channel_ids)
    added, added_fetched, skipped, failed = persist_fetched(
        db, notebook_id, all_docs, store_media=store_media
    )
    return [source_to_out(s) for s in added], added_fetched, len(added), skipped, failed
