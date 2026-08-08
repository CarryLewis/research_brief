"""LLM analysis for Knowledge Objects (email bundles and single documents)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..db import KnowledgeObject, SourceDoc
from ..schemas import AnalysisOut
from ..utils import dumps, loads
from . import knowledge as knowledge_svc
from . import llm as llm_svc


def analyze_email_bundle(
    *,
    subject: str,
    sender: str,
    email_text: str,
    articles: list[SourceDoc],
    output_language: str = "zh",
) -> AnalysisOut:
    article_blocks: list[str] = []
    for i, art in enumerate(articles, start=1):
        body = (art.raw_text or "")[:6000]
        article_blocks.append(
            f"### Article {i}\nTitle: {art.title}\nURL: {art.url or ''}\n\n{body}"
        )
    articles_blob = "\n\n".join(article_blocks) if article_blocks else "(no linked articles fetched)"
    lang = "Chinese" if (output_language or "zh").startswith("zh") else "English"
    system = (
        "You analyze newsletter emails and their linked articles for a personal knowledge system. "
        "Return a single JSON object with keys: "
        "summary (string), tags (string array of short topical labels), "
        "key_points (string array), entities (string array of concepts/people/diseases/tools), "
        "followup_urls (string array of useful URLs not already covered). "
        "Prefer secondary tags from: medicine, ai, cardiology, neurology, technology, economics, "
        "biology, product, research, clinical. "
        f"Write summary and key_points in {lang}."
    )
    user = (
        f"Email subject: {subject}\n"
        f"From: {sender}\n\n"
        f"Email body:\n{(email_text or '')[:8000]}\n\n"
        f"Linked articles:\n{articles_blob}"
    )
    data = llm_svc.chat_json(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=1500,
    )
    return _to_analysis(data)


def analyze_document(
    *,
    title: str,
    text: str,
    url: str | None = None,
    connector: str = "",
    kind: str = "article",
    output_language: str = "zh",
) -> AnalysisOut:
    """Analyze a single captured document into distilled KO fields."""
    lang = "Chinese" if (output_language or "zh").startswith("zh") else "English"
    system = (
        "You distill a captured research document into a Knowledge Object. "
        "Return a single JSON object with keys: "
        "summary (string, concise), tags (string array of short topical labels), "
        "key_points (string array, 3-7 items), entities (string array of concepts), "
        "followup_urls (string array). "
        "Prefer secondary tags from: medicine, ai, cardiology, neurology, technology, economics, "
        "biology, product, research, clinical. "
        "Do not invent facts not supported by the text. "
        f"Write summary and key_points in {lang}."
    )
    user = (
        f"Kind: {kind}\n"
        f"Connector: {connector}\n"
        f"Title: {title}\n"
        f"URL: {url or ''}\n\n"
        f"Text:\n{(text or '')[:10000]}"
    )
    data = llm_svc.chat_json(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=1200,
    )
    return _to_analysis(data)


def attach_analysis(
    db: Session, source: SourceDoc, analysis: AnalysisOut, *, status: str = "analyzed"
) -> None:
    meta = loads(source.metadata_json, {}) or {}
    meta["analysis"] = analysis.model_dump()
    source.metadata_json = dumps(meta)
    source.status = status
    db.commit()
    db.refresh(source)
    # Mirror into Knowledge Object
    ko = knowledge_svc.get_by_source(db, source.id)
    if ko is None:
        ko = knowledge_svc.upsert_from_source(db, source)
    knowledge_svc.apply_analysis(db, ko, analysis)


def attach_analysis_error(db: Session, source: SourceDoc, error: str) -> None:
    meta = loads(source.metadata_json, {}) or {}
    meta["analysis_error"] = error
    source.metadata_json = dumps(meta)
    if source.status == "ready":
        source.status = "partial"
    source.error = error[:2000]
    db.commit()
    db.refresh(source)
    ko = knowledge_svc.get_by_source(db, source.id)
    if ko:
        ko.status = "processing"
        db.commit()


def analyze_sources(
    db: Session,
    sources: list[SourceDoc],
    *,
    output_language: str = "zh",
) -> dict[str, AnalysisOut | None]:
    """Run per-document analysis for collect paths. Returns map source_id -> analysis."""
    results: dict[str, AnalysisOut | None] = {}
    for src in sources:
        if src.status == "failed":
            results[src.id] = None
            continue
        ko = knowledge_svc.get_by_source(db, src.id)
        kind = ko.kind if ko else knowledge_svc.infer_kind(
            src.connector, loads(src.metadata_json, {}) or {}
        )
        try:
            analysis = analyze_document(
                title=src.title,
                text=src.raw_text or "",
                url=src.url,
                connector=src.connector,
                kind=kind,
                output_language=output_language,
            )
            attach_analysis(db, src, analysis, status="analyzed")
            results[src.id] = analysis
        except Exception as exc:  # noqa: BLE001
            attach_analysis_error(db, src, str(exc))
            results[src.id] = None
    return results


def _to_analysis(data: dict[str, Any]) -> AnalysisOut:
    def _str_list(key: str) -> list[str]:
        val = data.get(key) or []
        if not isinstance(val, list):
            return []
        return [str(x).strip() for x in val if str(x).strip()]

    return AnalysisOut(
        summary=str(data.get("summary") or "").strip(),
        tags=_str_list("tags"),
        key_points=_str_list("key_points"),
        entities=_str_list("entities"),
        followup_urls=_str_list("followup_urls"),
    )
