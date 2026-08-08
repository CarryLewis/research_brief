"""Inbound email → link follow → LLM analyze → Content Lake + KO → Obsidian projection."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from ..config import get_settings
from ..connectors.base import FetchedDoc
from ..connectors.web import WebConnector
from ..db import Notebook, SourceDoc
from ..email_parse import email_body_text, extract_urls, select_article_urls
from ..schemas import (
    AnalysisOut,
    InboundEmailIn,
    InboundEmailResult,
    NotebookCreate,
)
from ..utils import content_hash, dumps, loads
from . import analyze as analyze_svc
from . import chunks as chunks_svc
from . import knowledge as knowledge_svc
from . import notebook as notebook_svc
from . import subscriptions as subs_svc
from . import workspace as workspace_svc
from .ingest import persist_fetched


def process_inbound_email(
    db: Session,
    payload: InboundEmailIn,
    *,
    vault_path: str | None = None,
    download_media: bool = True,
    run_analysis: bool = True,
    index_chunks: bool = True,
) -> InboundEmailResult:
    settings = get_settings()
    notebook = _resolve_inbound_notebook(db, vault_path=vault_path)
    vault = vault_path or notebook.vault_path or settings.default_vault_path

    sender = (payload.from_ or "").strip()
    matched = subs_svc.find_matching_subscription(db, sender)
    mode = (settings.subscription_mode or "open").lower().strip()
    if mode == "allowlist" and matched is None:
        return InboundEmailResult(
            notebook_id=notebook.id,
            rejected=True,
            reject_reason="sender not in enabled subscription catalog",
            vault_path=vault or None,
        )

    message_id = _normalize_message_id(payload.message_id, payload)
    existing = _find_by_message_id(db, notebook.id, message_id)
    if existing:
        meta = loads(existing.metadata_json, {}) or {}
        analysis = meta.get("analysis")
        article_ids = list(meta.get("article_ids") or [])
        return InboundEmailResult(
            notebook_id=notebook.id,
            email_source_id=existing.id,
            article_ids=article_ids,
            duplicate=True,
            skipped_duplicates=1,
            subscription_id=meta.get("subscription_id"),
            subscription_name=meta.get("subscription_name"),
            selected_urls=list(meta.get("selected_urls") or []),
            analysis=AnalysisOut.model_validate(analysis) if analysis else None,
            vault_path=vault or None,
        )

    body = email_body_text(text=payload.text, html=payload.html)
    subject = (payload.subject or "(No subject)").strip()
    raw_text = f"{subject}\n\nFrom: {sender}\nTo: {payload.to or ''}\n\n{body}".strip()

    email_meta: dict = {
        "source_kind": "email",
        "message_id": message_id,
        "from": sender,
        "to": payload.to or "",
        "has_html": bool(payload.html),
    }
    if matched:
        email_meta["subscription_id"] = matched.id
        email_meta["subscription_name"] = matched.name
        email_meta["subscription_tags"] = loads(matched.tags_json, []) or []

    email_doc = FetchedDoc(
        connector="email",
        title=subject,
        raw_text=raw_text,
        url=f"email://{message_id}",
        authors=sender or None,
        published_at=payload.received_at,
        metadata=email_meta,
    )
    added_orm, _added_fetched, skipped, failed = persist_fetched(
        db, notebook.id, [email_doc], store_media=download_media
    )
    if not added_orm:
        # race / message-id / content-hash collision → treat as duplicate
        existing = _find_by_message_id(db, notebook.id, message_id)
        if not existing:
            h = content_hash(raw_text)
            existing = (
                db.query(SourceDoc)
                .filter(
                    SourceDoc.notebook_id == notebook.id,
                    SourceDoc.content_hash == h,
                )
                .first()
            )
        if existing:
            meta = loads(existing.metadata_json, {}) or {}
            analysis = meta.get("analysis")
            return InboundEmailResult(
                notebook_id=notebook.id,
                email_source_id=existing.id,
                article_ids=list(meta.get("article_ids") or []),
                duplicate=True,
                skipped_duplicates=max(skipped, 1),
                selected_urls=list(meta.get("selected_urls") or []),
                analysis=AnalysisOut.model_validate(analysis) if analysis else None,
                vault_path=vault or None,
            )
        raise ValueError("Failed to persist inbound email")

    email_src = added_orm[0]
    all_urls = extract_urls(text=payload.text, html=payload.html)
    selected = select_article_urls(
        all_urls,
        max_links=max(0, int(settings.inbound_max_links)),
        sender=sender,
    )

    article_orm: list[SourceDoc] = []
    article_fetched: list[FetchedDoc] = []
    art_skipped = 0
    art_failed = 0
    if selected:
        web = WebConnector()
        docs = web.fetch_urls(selected)
        for doc in docs:
            meta = dict(doc.metadata or {})
            meta.update(
                {
                    "source_kind": "article",
                    "parent_message_id": message_id,
                    "parent_source_id": email_src.id,
                }
            )
            doc.metadata = meta
        article_orm, _article_fetched, art_skipped, art_failed = persist_fetched(
            db, notebook.id, docs, store_media=download_media
        )

    article_ids = [s.id for s in article_orm]
    email_meta = loads(email_src.metadata_json, {}) or {}
    email_meta["selected_urls"] = selected
    email_meta["extracted_url_count"] = len(all_urls)
    email_meta["article_ids"] = article_ids
    email_src.metadata_json = dumps(email_meta)
    db.commit()
    db.refresh(email_src)

    analysis: AnalysisOut | None = None
    analysis_error: str | None = None
    if run_analysis:
        try:
            analysis_cfg = loads(notebook.analysis_json, {}) or {}
            lang = analysis_cfg.get("output_language") or "zh"
            analysis = analyze_svc.analyze_email_bundle(
                subject=subject,
                sender=sender,
                email_text=body,
                articles=article_orm,
                output_language=lang,
            )
            analyze_svc.attach_analysis(db, email_src, analysis, status="analyzed")
            for art in article_orm:
                if art.status in {"ready", "analyzed", "partial"}:
                    analyze_svc.attach_analysis(db, art, analysis, status="analyzed")
        except Exception as exc:  # noqa: BLE001
            analysis_error = str(exc)
            analyze_svc.attach_analysis_error(db, email_src, analysis_error)

    # Ensure Resource KOs exist even when analysis was skipped
    for src in [email_src, *article_orm]:
        if knowledge_svc.get_by_source(db, src.id) is None:
            knowledge_svc.upsert_from_source(
                db, src, store_lake=True, store_media=download_media
            )

    # Constitution: do not mirror Resources into Obsidian — scaffold only
    index_path = None
    if vault:
        try:
            from pathlib import Path

            from ..utils import workspace_config_dict

            root = Path(vault).expanduser()
            root.mkdir(parents=True, exist_ok=True)
            cfg = workspace_config_dict()
            if cfg.get("scaffold_folders", True):
                workspace_svc.ensure_scaffold(root, cfg)
            index_path = str(root)
            if not notebook.vault_path:
                notebook.vault_path = str(root)
                db.commit()
        except Exception as exc:  # noqa: BLE001
            if analysis_error:
                analysis_error = f"{analysis_error}; vault scaffold: {exc}"
            else:
                analysis_error = f"vault scaffold: {exc}"

    if index_chunks:
        to_index = [email_src] + article_orm
        chunks_svc.index_sources(db, to_index)

    return InboundEmailResult(
        notebook_id=notebook.id,
        email_source_id=email_src.id,
        article_ids=article_ids,
        duplicate=False,
        subscription_id=matched.id if matched else None,
        subscription_name=matched.name if matched else None,
        added=len(added_orm) + len(article_orm),
        skipped_duplicates=skipped + art_skipped,
        failed=failed + art_failed,
        selected_urls=selected,
        analysis=analysis,
        analysis_error=analysis_error,
        vault_path=vault or None,
        index_path=index_path,
    )


def _resolve_inbound_notebook(db: Session, *, vault_path: str | None) -> Notebook:
    settings = get_settings()
    if settings.inbound_notebook_id:
        nb = notebook_svc.get_notebook(db, settings.inbound_notebook_id)
        if nb:
            if vault_path and not nb.vault_path:
                nb.vault_path = vault_path
                db.commit()
                db.refresh(nb)
            return nb
    # Prefer an existing notebook with the inbound topic title
    topic = settings.inbound_topic or "订阅收件"
    existing = (
        db.query(Notebook)
        .filter(Notebook.topic == topic)
        .order_by(Notebook.updated_at.desc())
        .first()
    )
    if existing:
        if vault_path and not existing.vault_path:
            existing.vault_path = vault_path
            db.commit()
            db.refresh(existing)
        return existing
    out = notebook_svc.create_notebook(
        db,
        NotebookCreate(
            title=topic,
            topic=topic,
            vault_path=vault_path or settings.default_vault_path or None,
        ),
    )
    nb = notebook_svc.get_notebook(db, out.id)
    assert nb is not None
    return nb


def _normalize_message_id(message_id: str | None, payload: InboundEmailIn) -> str:
    mid = (message_id or "").strip()
    if mid:
        mid = mid.strip("<>").strip()
        if mid:
            return mid
    # Synthetic stable id from envelope fields
    basis = "|".join(
        [
            payload.from_ or "",
            payload.to or "",
            payload.subject or "",
            payload.received_at or "",
            (payload.text or "")[:500],
            (payload.html or "")[:500],
        ]
    )
    return "gen-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def _find_by_message_id(db: Session, notebook_id: str, message_id: str) -> SourceDoc | None:
    # Prefer url-based dedup key
    by_url = (
        db.query(SourceDoc)
        .filter(
            SourceDoc.notebook_id == notebook_id,
            SourceDoc.url == f"email://{message_id}",
        )
        .first()
    )
    if by_url:
        return by_url
    # Fallback scan recent email docs
    rows = (
        db.query(SourceDoc)
        .filter(SourceDoc.notebook_id == notebook_id, SourceDoc.connector == "email")
        .order_by(SourceDoc.created_at.desc())
        .limit(200)
        .all()
    )
    for row in rows:
        meta = loads(row.metadata_json, {}) or {}
        if meta.get("message_id") == message_id:
            return row
    return None
