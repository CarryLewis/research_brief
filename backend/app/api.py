from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from datetime import datetime

from .schemas import (
    AcceptProposalRequest,
    AcceptSuggestionRequest,
    AskRequest,
    AskResult,
    CollectRequest,
    CollectResult,
    ConceptCentralOut,
    ConceptSuggestionOut,
    DemoteRequest,
    DigestRequest,
    DigestResult,
    ExportRequest,
    ExportResult,
    GraphSuggestLinksRequest,
    GraphSyncRequest,
    InboundEmailIn,
    InboundEmailResult,
    InsightCreate,
    InsightDraftRequest,
    InsightOut,
    KnowledgeObjectOut,
    LibrarySaveRequest,
    LibrarySaveResult,
    LifecycleEventOut,
    LifecycleProposalOut,
    PromoteRequest,
    QuestionCreate,
    QuestionOut,
    QuestionUpdate,
    ReflectionAssistRequest,
    ReflectionCreate,
    ReflectionOut,
    ReflectionUpdate,
    SearchRequest,
    SearchResult,
    SignalFilterRequest,
    SignalFilterResult,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
)
from .services import channels as channels_svc
from .services import collect as collect_svc
from .services import digest as digest_svc
from .services import email_pipeline as email_pipeline_svc
from .services import knowledge as knowledge_svc
from .services import graph_engine as graph_svc
from .services import library_writer as library_svc
from .services import lifecycle as life_svc
from .services import lifecycle_ai as life_ai
from .services import notebook as notebook_svc
from .services import retrieve as retrieve_svc
from .services import subscriptions as subs_svc
from .services import thinking as thinking_svc
from .services import workspace as workspace_svc
from .utils import loads

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    settings = get_settings()
    return {
        "ok": True,
        "service": "research-brief",
        "mode": "library-v1",
        "library_auth_required": bool((settings.library_api_token or "").strip()),
    }


@router.get("/channels")
def list_channels():
    return {"channels": channels_svc.list_channels_for_api()}


def _verify_library_token(
    authorization: Annotated[str | None, Header()] = None,
    x_library_token: Annotated[str | None, Header(alias="X-Library-Token")] = None,
) -> None:
    """Require shared token when LIBRARY_API_TOKEN is configured; open if unset (local dev)."""
    settings = get_settings()
    expected = (settings.library_api_token or "").strip()
    if not expected:
        return
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    elif x_library_token:
        provided = x_library_token.strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(401, "Invalid library API token")


@router.post("/library/save", response_model=LibrarySaveResult)
def library_save(
    payload: LibrarySaveRequest,
    _: None = Depends(_verify_library_token),
):
    """Save HTML / URL / Markdown into Obsidian Library/Articles (v1 Capture)."""
    settings = get_settings()
    vault = (payload.vault_path or settings.default_vault_path or "").strip()
    if not vault:
        raise HTTPException(400, "vault_path is required (or set DEFAULT_VAULT_PATH)")

    source_type = (payload.source_type or "article").strip().lower()
    if source_type not in {"article", "email"}:
        raise HTTPException(400, "source_type must be article or email")
    on_dup = (payload.on_duplicate or "update").strip().lower()
    if on_dup not in {"update", "skip", "new"}:
        raise HTTPException(400, "on_duplicate must be update, skip, or new")

    try:
        result = library_svc.save(
            vault,
            html=payload.html,
            url=payload.url,
            body_md=payload.body_md,
            title=payload.title,
            authors=payload.authors,
            tags=payload.tags,
            source_type=source_type,  # type: ignore[arg-type]
            visibility=payload.visibility or "private",
            status=payload.status or "inbox",
            download_images=payload.download_images,
            on_duplicate=on_dup,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Library save failed: {exc}") from exc

    return LibrarySaveResult(
        ok=True,
        item_id=result.item_id,
        title=result.title,
        note_path=str(result.note_path),
        note_relpath=result.note_relpath,
        source_url=result.source_url or payload.url,
        created=result.created,
        updated=result.updated,
        skipped=result.skipped,
        images_downloaded=result.images_downloaded,
        image_errors=result.image_errors,
        vault_path=str(Path(vault).expanduser()),
    )


@router.post("/collect", response_model=CollectResult)
def collect(payload: CollectRequest, db: Session = Depends(get_db)):
    """Capture → Content Lake + Resource KOs in the Knowledge Database (not Obsidian)."""
    settings = get_settings()
    vault = payload.vault_path or settings.default_vault_path
    if not vault:
        raise HTTPException(400, "vault_path is required (or set DEFAULT_VAULT_PATH)")
    try:
        return collect_svc.run_collect(db, payload, vault_path=vault)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/notebooks/{notebook_id}/sync-workspace", response_model=ExportResult)
@router.post("/notebooks/{notebook_id}/export-knowledge", response_model=ExportResult)
@router.post("/notebooks/{notebook_id}/export-raw", response_model=ExportResult)
def sync_workspace(notebook_id: str, payload: ExportRequest, db: Session = Depends(get_db)):
    """Sync promoted workspace notes only (Concept/Project/Reflection/Book)."""
    nb = notebook_svc.get_notebook(db, notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    settings = get_settings()
    vault = payload.vault_path or nb.vault_path or settings.default_vault_path
    if not vault:
        raise HTTPException(400, "vault_path is required")
    try:
        return workspace_svc.sync_workspace_notes(
            db, vault_path=vault, notebook_id=notebook_id
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _ko_out(ko) -> KnowledgeObjectOut:
    from .utils import loads as _loads

    return KnowledgeObjectOut(
        id=ko.id,
        notebook_id=ko.notebook_id,
        kind=ko.kind,
        workspace_role=ko.workspace_role or "resource",
        graph_eligible=bool(ko.graph_eligible),
        title=ko.title,
        summary=ko.summary or "",
        source_url=ko.source_url,
        tags=_loads(ko.tags_json, []) or [],
        entities=_loads(ko.entities_json, []) or [],
        vault_path=ko.vault_path,
        status=ko.status,
        lifecycle_stage=getattr(ko, "lifecycle_stage", None) or "resource",
        evidence_score=float(getattr(ko, "evidence_score", 0) or 0),
        confidence=float(getattr(ko, "confidence", 0) or 0),
        maturity=getattr(ko, "maturity", None) or "",
    )


@router.get("/knowledge/suggestions", response_model=list[ConceptSuggestionOut])
def list_suggestions(
    notebook_id: str | None = None,
    db: Session = Depends(get_db),
):
    rows = knowledge_svc.list_concept_suggestions(db, notebook_id=notebook_id)
    return [
        ConceptSuggestionOut(
            id=r.id,
            notebook_id=r.notebook_id,
            entity_name=r.entity_name,
            mention_count=r.mention_count,
            status=r.status,
            message=r.message,
        )
        for r in rows
    ]


@router.post("/knowledge/suggestions/{suggestion_id}/accept", response_model=KnowledgeObjectOut)
def accept_suggestion(
    suggestion_id: str,
    payload: AcceptSuggestionRequest,
    db: Session = Depends(get_db),
):
    from .db import ConceptSuggestion

    sug = db.query(ConceptSuggestion).filter(ConceptSuggestion.id == suggestion_id).first()
    if not sug:
        raise HTTPException(404, "Suggestion not found")
    settings = get_settings()
    vault = payload.vault_path or settings.default_vault_path
    try:
        ko = knowledge_svc.create_concept_from_suggestion(
            db,
            sug,
            vault_path=vault,
            notebook_id=payload.notebook_id or sug.notebook_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _ko_out(ko)


@router.post("/knowledge/{ko_id}/promote", response_model=KnowledgeObjectOut)
def promote_knowledge(ko_id: str, payload: PromoteRequest, db: Session = Depends(get_db)):
    ko = knowledge_svc.get_by_id(db, ko_id)
    if not ko:
        raise HTTPException(404, "Knowledge object not found")
    settings = get_settings()
    vault = payload.vault_path or settings.default_vault_path
    try:
        ko = knowledge_svc.promote(
            db,
            ko,
            payload.role,
            title=payload.title,
            vault_path=vault,
            sync=payload.sync,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _ko_out(ko)


@router.post("/knowledge/{ko_id}/demote", response_model=KnowledgeObjectOut)
def demote_knowledge(ko_id: str, payload: DemoteRequest, db: Session = Depends(get_db)):
    ko = knowledge_svc.get_by_id(db, ko_id)
    if not ko:
        raise HTTPException(404, "Knowledge object not found")
    settings = get_settings()
    vault = payload.vault_path or settings.default_vault_path
    ko = knowledge_svc.demote(
        db,
        ko,
        archive_file=payload.archive_file,
        vault_path=vault,
    )
    return _ko_out(ko)


@router.get("/knowledge/{ko_id}", response_model=KnowledgeObjectOut)
def get_knowledge(ko_id: str, db: Session = Depends(get_db)):
    ko = knowledge_svc.get_by_id(db, ko_id)
    if not ko:
        raise HTTPException(404, "Knowledge object not found")
    return _ko_out(ko)


# --- Lifecycle Engine ---


@router.get("/lifecycle/evolution", response_model=list[LifecycleEventOut])
def lifecycle_evolution(ko_id: str, db: Session = Depends(get_db)):
    events = life_svc.list_evolution(db, ko_id)
    return [
        LifecycleEventOut(
            id=e.id,
            ko_id=e.ko_id,
            from_stage=e.from_stage,
            to_stage=e.to_stage,
            from_maturity=e.from_maturity,
            to_maturity=e.to_maturity,
            trigger=e.trigger,
            actor=e.actor,
            payload=loads(e.payload_json, {}) or {},
            created_at=e.created_at,
        )
        for e in events
    ]


@router.get("/lifecycle/proposals", response_model=list[LifecycleProposalOut])
def lifecycle_proposals(notebook_id: str | None = None, db: Session = Depends(get_db)):
    rows = life_svc.list_proposals(db, notebook_id=notebook_id)
    return [
        LifecycleProposalOut(
            id=r.id,
            ko_id=r.ko_id,
            notebook_id=r.notebook_id,
            proposed_stage=r.proposed_stage,
            proposed_maturity=r.proposed_maturity,
            reason=r.reason,
            score=r.score,
            status=r.status,
        )
        for r in rows
    ]


@router.post("/lifecycle/proposals/{proposal_id}/accept", response_model=KnowledgeObjectOut)
def accept_lifecycle_proposal(
    proposal_id: str, payload: AcceptProposalRequest, db: Session = Depends(get_db)
):
    from .db import LifecycleProposal

    prop = db.query(LifecycleProposal).filter(LifecycleProposal.id == proposal_id).first()
    if not prop:
        raise HTTPException(404, "Proposal not found")
    settings = get_settings()
    vault = payload.vault_path or settings.default_vault_path
    try:
        ko = life_svc.accept_proposal(
            db, prop, sync_workspace=payload.sync_workspace, vault_path=vault
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _ko_out(ko)


@router.post("/lifecycle/proposals/{proposal_id}/dismiss", response_model=LifecycleProposalOut)
def dismiss_lifecycle_proposal(proposal_id: str, db: Session = Depends(get_db)):
    from .db import LifecycleProposal

    prop = db.query(LifecycleProposal).filter(LifecycleProposal.id == proposal_id).first()
    if not prop:
        raise HTTPException(404, "Proposal not found")
    prop = life_svc.dismiss_proposal(db, prop)
    return LifecycleProposalOut(
        id=prop.id,
        ko_id=prop.ko_id,
        notebook_id=prop.notebook_id,
        proposed_stage=prop.proposed_stage,
        proposed_maturity=prop.proposed_maturity,
        reason=prop.reason,
        score=prop.score,
        status=prop.status,
    )


@router.post("/lifecycle/evaluate")
def lifecycle_evaluate(notebook_id: str | None = None, db: Session = Depends(get_db)):
    props = life_svc.evaluate_workspace(db, notebook_id)
    return {"proposals": len(props), "ids": [p.id for p in props]}


@router.get("/lifecycle/concepts/central", response_model=list[ConceptCentralOut])
def lifecycle_central_concepts(
    notebook_id: str | None = None, limit: int = 20, db: Session = Depends(get_db)
):
    rows = life_svc.list_central_concepts(db, notebook_id=notebook_id, limit=limit)
    return [
        ConceptCentralOut(
            id=ko.id,
            title=ko.title,
            maturity_level=prof.maturity_level,
            promotion_score=prof.promotion_score,
            mention_count=prof.mention_count,
            reflection_count=prof.reflection_count,
            resource_count=prof.resource_count,
            project_count=prof.project_count,
        )
        for ko, prof in rows
    ]


@router.get("/lifecycle/questions", response_model=list[QuestionOut])
def lifecycle_questions(
    notebook_id: str | None = None,
    status: str | None = "open",
    db: Session = Depends(get_db),
):
    rows = thinking_svc.list_questions(db, notebook_id=notebook_id, status=status)
    return [
        QuestionOut(
            id=ko.id,
            title=ko.title,
            statement=q.statement,
            status=q.status,
            priority=q.priority,
            owner=q.owner,
            answer_summary=q.answer_summary,
        )
        for ko, q in rows
    ]


@router.get("/lifecycle/insights", response_model=list[InsightOut])
def lifecycle_insights(notebook_id: str | None = None, db: Session = Depends(get_db)):
    rows = thinking_svc.list_insights(db, notebook_id=notebook_id)
    return [
        InsightOut(
            id=ko.id,
            title=ko.title,
            statement=ins.statement,
            evidence_md=ins.evidence_md,
            confidence=ins.confidence,
            status=ins.status,
        )
        for ko, ins in rows
    ]


@router.get("/lifecycle/changes", response_model=list[LifecycleEventOut])
def lifecycle_changes(
    since: datetime,
    notebook_id: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    events = life_svc.list_changes_since(
        db, since=since, notebook_id=notebook_id, limit=limit
    )
    return [
        LifecycleEventOut(
            id=e.id,
            ko_id=e.ko_id,
            from_stage=e.from_stage,
            to_stage=e.to_stage,
            from_maturity=e.from_maturity,
            to_maturity=e.to_maturity,
            trigger=e.trigger,
            actor=e.actor,
            payload=loads(e.payload_json, {}) or {},
            created_at=e.created_at,
        )
        for e in events
    ]


@router.post("/lifecycle/backfill")
def lifecycle_backfill(db: Session = Depends(get_db)):
    return life_svc.backfill_lifecycle(db)


@router.post("/lifecycle/signals/{ko_id}/filter", response_model=SignalFilterResult)
def lifecycle_filter_signal(
    ko_id: str, payload: SignalFilterRequest, db: Session = Depends(get_db)
):
    from .db import KnowledgeObject

    ko = db.query(KnowledgeObject).filter(KnowledgeObject.id == ko_id).first()
    if not ko:
        raise HTTPException(404, "Knowledge object not found")
    result = life_ai.filter_signal(
        db, ko, apply=payload.apply, use_llm=payload.use_llm
    )
    return SignalFilterResult(**result)


@router.post("/lifecycle/reflections/{reflection_id}/assist")
def lifecycle_reflection_assist(
    reflection_id: str, payload: ReflectionAssistRequest, db: Session = Depends(get_db)
):
    try:
        return life_ai.suggest_questions_from_reflection(
            db,
            reflection_id,
            create=payload.create_questions,
            use_llm=payload.use_llm,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/lifecycle/projects/{project_id}/context")
def lifecycle_project_context(project_id: str, db: Session = Depends(get_db)):
    try:
        return life_ai.project_context_pack(db, project_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/lifecycle/insights/draft")
def lifecycle_insight_draft(payload: InsightDraftRequest, db: Session = Depends(get_db)):
    return life_ai.draft_insight(
        db,
        notebook_id=payload.notebook_id,
        supporting_ko_ids=payload.supporting_ko_ids,
        question_id=payload.question_id,
        use_llm=payload.use_llm,
        accept=payload.accept,
    )


@router.get("/lifecycle/questions/{question_id}/reading")
def lifecycle_question_reading(question_id: str, db: Session = Depends(get_db)):
    try:
        return life_ai.suggest_reading_for_question(db, question_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# --- Knowledge Graph Engine (cognitive projection; no visualization) ---


@router.post("/graph/sync")
def graph_sync(payload: GraphSyncRequest | None = None, db: Session = Depends(get_db)):
    nb = payload.notebook_id if payload else None
    return graph_svc.sync_graph(db, nb)


@router.get("/graph/view/{view_id}")
def graph_view(
    view_id: str,
    notebook_id: str | None = None,
    fresh: bool = False,
    db: Session = Depends(get_db),
):
    return graph_svc.get_view(db, view_id, notebook_id=notebook_id, fresh=fresh)


@router.get("/graph/neighborhood")
def graph_neighborhood(
    ko_id: str,
    depth: int = 1,
    notebook_id: str | None = None,
    fresh: bool = False,
    db: Session = Depends(get_db),
):
    try:
        return graph_svc.neighborhood(
            db, ko_id, depth=depth, notebook_id=notebook_id, fresh=fresh
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/graph/path")
def graph_path(
    from_id: str,
    to_id: str,
    notebook_id: str | None = None,
    db: Session = Depends(get_db),
):
    return graph_svc.shortest_path(db, from_id, to_id, notebook_id=notebook_id)


@router.get("/graph/concept/{ko_id}/history")
def graph_concept_history(ko_id: str, db: Session = Depends(get_db)):
    return graph_svc.concept_history(db, ko_id)


@router.get("/graph/project/{project_id}")
def graph_project(project_id: str, fresh: bool = False, db: Session = Depends(get_db)):
    try:
        return graph_svc.project_graph(db, project_id, fresh=fresh)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/graph/timeline")
def graph_timeline(
    since: datetime | None = None,
    notebook_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return graph_svc.timeline(db, since=since, notebook_id=notebook_id, limit=limit)


@router.get("/graph/questions/open")
def graph_open_questions(notebook_id: str | None = None, db: Session = Depends(get_db)):
    return graph_svc.open_questions_graph(db, notebook_id=notebook_id)


@router.get("/graph/metrics")
def graph_metrics(
    notebook_id: str | None = None,
    series: bool = False,
    db: Session = Depends(get_db),
):
    return graph_svc.get_metrics(db, notebook_id=notebook_id, series=series)


@router.get("/graph/stats")
def graph_stats_endpoint(notebook_id: str | None = None, db: Session = Depends(get_db)):
    return graph_svc.graph_stats(db, notebook_id=notebook_id)


@router.get("/graph/orphans")
def graph_orphans(notebook_id: str | None = None, db: Session = Depends(get_db)):
    return {"orphans": graph_svc.list_orphans(db, notebook_id=notebook_id)}


@router.post("/graph/ai/suggest-links")
def graph_suggest_links(payload: GraphSuggestLinksRequest, db: Session = Depends(get_db)):
    return {
        "proposals": graph_svc.suggest_graph_links(
            db, notebook_id=payload.notebook_id, use_llm=payload.use_llm
        )
    }


# --- Thinking CRUD ---


@router.post("/reflections", response_model=ReflectionOut)
def create_reflection(payload: ReflectionCreate, db: Session = Depends(get_db)):
    settings = get_settings()
    vault = payload.vault_path or settings.default_vault_path
    try:
        ko, ref = thinking_svc.create_reflection(
            db,
            notebook_id=payload.notebook_id,
            title=payload.title,
            body_md=payload.body_md,
            author=payload.author,
            importance=payload.importance,
            related_ko_ids=payload.related_ko_ids,
            vault_path=vault,
            sync=payload.sync,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ReflectionOut(
        id=ko.id,
        title=ko.title,
        body_md=ref.body_md,
        author=ref.author,
        importance=ref.importance,
        status=ref.status,
        vault_path=ko.vault_path,
    )


@router.patch("/reflections/{reflection_id}", response_model=ReflectionOut)
def update_reflection(
    reflection_id: str, payload: ReflectionUpdate, db: Session = Depends(get_db)
):
    settings = get_settings()
    vault = payload.vault_path or settings.default_vault_path
    try:
        ko, ref = thinking_svc.update_reflection(
            db,
            reflection_id,
            title=payload.title,
            body_md=payload.body_md,
            importance=payload.importance,
            status=payload.status,
            vault_path=vault,
            sync=payload.sync,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ReflectionOut(
        id=ko.id,
        title=ko.title,
        body_md=ref.body_md,
        author=ref.author,
        importance=ref.importance,
        status=ref.status,
        vault_path=ko.vault_path,
    )


@router.post("/questions", response_model=QuestionOut)
def create_question(payload: QuestionCreate, db: Session = Depends(get_db)):
    try:
        ko, q = thinking_svc.create_question(
            db,
            notebook_id=payload.notebook_id,
            statement=payload.statement,
            title=payload.title,
            priority=payload.priority,
            owner=payload.owner,
            related_ko_ids=payload.related_ko_ids,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return QuestionOut(
        id=ko.id,
        title=ko.title,
        statement=q.statement,
        status=q.status,
        priority=q.priority,
        owner=q.owner,
        answer_summary=q.answer_summary,
    )


@router.patch("/questions/{question_id}", response_model=QuestionOut)
def update_question(question_id: str, payload: QuestionUpdate, db: Session = Depends(get_db)):
    try:
        ko, q = thinking_svc.update_question(
            db,
            question_id,
            statement=payload.statement,
            status=payload.status,
            priority=payload.priority,
            answer_summary=payload.answer_summary,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return QuestionOut(
        id=ko.id,
        title=ko.title,
        statement=q.statement,
        status=q.status,
        priority=q.priority,
        owner=q.owner,
        answer_summary=q.answer_summary,
    )


@router.post("/insights", response_model=InsightOut)
def create_insight(payload: InsightCreate, db: Session = Depends(get_db)):
    settings = get_settings()
    vault = payload.vault_path or settings.default_vault_path
    try:
        ko, ins = thinking_svc.create_insight(
            db,
            notebook_id=payload.notebook_id,
            statement=payload.statement,
            evidence_md=payload.evidence_md,
            confidence=payload.confidence,
            title=payload.title,
            supporting_ko_ids=payload.supporting_ko_ids,
            answers_question_id=payload.answers_question_id,
            vault_path=vault,
            sync_as_reflection=payload.sync_as_reflection,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return InsightOut(
        id=ko.id,
        title=ko.title,
        statement=ins.statement,
        evidence_md=ins.evidence_md,
        confidence=ins.confidence,
        status=ins.status,
    )


def _verify_inbound_secret(
    authorization: Annotated[str | None, Header()] = None,
    x_inbound_secret: Annotated[str | None, Header(alias="X-Inbound-Secret")] = None,
    secret: Annotated[str | None, Query()] = None,
) -> None:
    settings = get_settings()
    expected = (settings.inbound_webhook_secret or "").strip()
    if not expected:
        raise HTTPException(
            503,
            "INBOUND_WEBHOOK_SECRET is not configured; refuse inbound email",
        )
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    elif x_inbound_secret:
        provided = x_inbound_secret.strip()
    elif secret:
        provided = secret.strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(401, "Invalid inbound webhook secret")


@router.post("/inbound/email", response_model=InboundEmailResult)
async def inbound_email(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_inbound_secret),
):
    """Push entry for forwarded / webhook email. Accepts JSON or Mailgun-style form."""
    content_type = (request.headers.get("content-type") or "").lower()
    try:
        if "application/json" in content_type:
            data = await request.json()
            payload = InboundEmailIn.model_validate(data)
        elif (
            "multipart/form-data" in content_type
            or "application/x-www-form-urlencoded" in content_type
        ):
            form = await request.form()
            payload = _mailgun_form_to_inbound(form)
        else:
            # try JSON first, then form
            try:
                data = await request.json()
                payload = InboundEmailIn.model_validate(data)
            except Exception:  # noqa: BLE001
                form = await request.form()
                payload = _mailgun_form_to_inbound(form)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Invalid inbound payload: {exc}") from exc

    settings = get_settings()
    vault = settings.default_vault_path or None
    try:
        return email_pipeline_svc.process_inbound_email(db, payload, vault_path=vault)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/search", response_model=SearchResult)
def search(payload: SearchRequest, db: Session = Depends(get_db)):
    nb = notebook_svc.get_notebook(db, payload.notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    return retrieve_svc.search(db, payload.notebook_id, payload.query, top_k=payload.top_k)


@router.post("/ask", response_model=AskResult)
def ask(payload: AskRequest, db: Session = Depends(get_db)):
    nb = notebook_svc.get_notebook(db, payload.notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    analysis = loads(nb.analysis_json, {}) or {}
    lang = analysis.get("output_language") or "zh"
    try:
        return retrieve_svc.ask(
            db,
            payload.notebook_id,
            payload.question,
            top_k=payload.top_k,
            save_brief=payload.save_brief,
            output_language=lang,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Ask failed: {exc}") from exc


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def list_subscriptions(
    enabled_only: bool = False,
    db: Session = Depends(get_db),
):
    return subs_svc.list_subscriptions(db, enabled_only=enabled_only)


@router.post("/subscriptions", response_model=SubscriptionOut)
def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_db)):
    try:
        return subs_svc.create_subscription(db, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/subscriptions/{sub_id}", response_model=SubscriptionOut)
def update_subscription(
    sub_id: str, payload: SubscriptionUpdate, db: Session = Depends(get_db)
):
    row = subs_svc.get_subscription(db, sub_id)
    if not row:
        raise HTTPException(404, "Subscription not found")
    try:
        return subs_svc.update_subscription(db, row, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/subscriptions/{sub_id}")
def delete_subscription(sub_id: str, db: Session = Depends(get_db)):
    row = subs_svc.get_subscription(db, sub_id)
    if not row:
        raise HTTPException(404, "Subscription not found")
    subs_svc.delete_subscription(db, row)
    return {"ok": True, "id": sub_id}


@router.post("/digest/run", response_model=DigestResult)
def run_digest(payload: DigestRequest, db: Session = Depends(get_db)):
    try:
        return digest_svc.run_digest(
            db,
            period=payload.period,
            notebook_id=payload.notebook_id,
            send=payload.send and not payload.dry_run,
            dry_run=payload.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Digest failed: {exc}") from exc


def _mailgun_form_to_inbound(form) -> InboundEmailIn:
    """Map Mailgun Inbound Parse (and similar) fields to InboundEmailIn."""
    get = form.get
    message_id = get("Message-Id") or get("message-id") or get("Message-ID")
    return InboundEmailIn.model_validate(
        {
            "message_id": message_id,
            "from": get("from") or get("sender") or "",
            "to": get("To") or get("recipient") or get("to") or "",
            "subject": get("subject") or "(No subject)",
            "text": get("body-plain") or get("text") or get("stripped-text"),
            "html": get("body-html") or get("html") or get("stripped-html"),
            "received_at": get("Date") or get("timestamp"),
        }
    )
