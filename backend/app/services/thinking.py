"""CRUD for first-class Reflection, Question, Insight (+ Obsidian sync rules)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db import Insight, KnowledgeObject, Question, Reflection, utcnow
from ..utils import content_hash, dumps, lifecycle_config_dict, new_id
from . import lifecycle as life_svc
from . import workspace as workspace_svc


def _new_ko(
    db: Session,
    *,
    notebook_id: str,
    kind: str,
    title: str,
    lifecycle_stage: str,
    workspace_role: str,
    summary: str = "",
    confidence: float = 0.0,
) -> KnowledgeObject:
    ko = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=notebook_id,
        kind=kind,
        title=title,
        summary=summary,
        key_points_json="[]",
        status="ready",
        connector="manual",
        content_hash=content_hash(title + summary),
        tags_json="[]",
        entities_json="[]",
        metadata_json="{}",
        workspace_role=workspace_role,
        graph_eligible=1 if workspace_role in {
            "concept",
            "project",
            "reflection",
            "book",
            "thinking",
            "research",
            "information",
            "insight",
            "question",
        } else 0,
        lifecycle_stage=lifecycle_stage,
        maturity="candidate" if kind == "concept" else "",
        confidence=confidence,
        lifecycle_updated_at=utcnow(),
    )
    db.add(ko)
    db.commit()
    db.refresh(ko)
    life_svc.record_event(
        db,
        ko,
        from_stage="",
        to_stage=lifecycle_stage,
        to_maturity=ko.maturity,
        trigger="user_reflect" if kind == "reflection" else "user_promote",
        actor="user",
        payload={"kind": kind},
    )
    return ko


def create_reflection(
    db: Session,
    *,
    notebook_id: str,
    title: str,
    body_md: str = "",
    author: str = "",
    importance: str = "medium",
    related_ko_ids: list[str] | None = None,
    vault_path: str | None = None,
    sync: bool = True,
) -> tuple[KnowledgeObject, Reflection]:
    ko = _new_ko(
        db,
        notebook_id=notebook_id,
        kind="reflection",
        title=title,
        lifecycle_stage="reflection",
        workspace_role="reflection",
        summary=(body_md or "")[:500],
    )
    ref = Reflection(
        id=ko.id,
        body_md=body_md or "",
        author=author or "",
        importance=importance,
        status="active",
        open_questions_json="[]",
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)
    for rid in related_ko_ids or []:
        life_svc.create_edge(
            db,
            from_ko_id=ko.id,
            to_ko_id=rid,
            edge_type="reflects_on",
            from_type="reflection",
            to_type="ko",
            created_by="user",
        )
    if sync and vault_path:
        # Prefill summary from body for search/graph; vault gets freeform body_md
        ko.summary = (body_md or "")[:800]
        db.commit()
        workspace_svc.sync_note(db, ko, vault_path=vault_path, force=True)
    # Lifecycle AI: suggest open questions (heuristic; LLM if configured)
    ai_cfg = (lifecycle_config_dict() or {}).get("ai") or {}
    if ai_cfg.get("suggest_questions_on_reflection", True):
        try:
            from . import lifecycle_ai as life_ai

            life_ai.suggest_questions_from_reflection(
                db,
                ko.id,
                create=False,
                use_llm=bool(ai_cfg.get("use_llm_when_configured")),
            )
        except Exception:  # noqa: BLE001
            pass
    life_svc.evaluate_workspace(db, notebook_id)
    try:
        from . import graph_engine as graph_svc

        graph_svc.maybe_auto_sync(db, notebook_id)
    except Exception:  # noqa: BLE001
        pass
    return ko, ref


def update_reflection(
    db: Session,
    reflection_id: str,
    *,
    title: str | None = None,
    body_md: str | None = None,
    importance: str | None = None,
    status: str | None = None,
    vault_path: str | None = None,
    sync: bool = True,
) -> tuple[KnowledgeObject, Reflection]:
    ref = db.query(Reflection).filter(Reflection.id == reflection_id).first()
    if not ref:
        raise ValueError("Reflection not found")
    ko = db.query(KnowledgeObject).filter(KnowledgeObject.id == reflection_id).first()
    if not ko:
        raise ValueError("Knowledge object not found")
    if title is not None:
        ko.title = title
    if body_md is not None:
        ref.body_md = body_md
        ko.summary = body_md[:800]
    if importance is not None:
        ref.importance = importance
    if status is not None:
        ref.status = status
    db.commit()
    if sync and vault_path:
        # API owns the write — force past preserve_existing_reflection_files
        workspace_svc.sync_note(db, ko, vault_path=vault_path, force=True)
    db.refresh(ko)
    db.refresh(ref)
    return ko, ref


def create_question(
    db: Session,
    *,
    notebook_id: str,
    statement: str,
    title: str | None = None,
    priority: str = "P2",
    owner: str = "",
    related_ko_ids: list[str] | None = None,
) -> tuple[KnowledgeObject, Question]:
    title = title or statement[:120]
    ko = _new_ko(
        db,
        notebook_id=notebook_id,
        kind="question",
        title=title,
        lifecycle_stage="question",
        workspace_role="resource",  # DB-first, no auto vault
        summary=statement,
    )
    q = Question(
        id=ko.id,
        statement=statement,
        status="open",
        priority=priority,
        owner=owner,
        answer_summary="",
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    for rid in related_ko_ids or []:
        life_svc.create_edge(
            db,
            from_ko_id=ko.id,
            to_ko_id=rid,
            edge_type="about",
            from_type="question",
            to_type="ko",
            created_by="user",
        )
    try:
        from . import graph_engine as graph_svc

        graph_svc.maybe_auto_sync(db, notebook_id)
    except Exception:  # noqa: BLE001
        pass
    return ko, q


def update_question(
    db: Session,
    question_id: str,
    *,
    statement: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    answer_summary: str | None = None,
) -> tuple[KnowledgeObject, Question]:
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise ValueError("Question not found")
    ko = db.query(KnowledgeObject).filter(KnowledgeObject.id == question_id).first()
    if not ko:
        raise ValueError("Knowledge object not found")
    if statement is not None:
        q.statement = statement
        ko.summary = statement
    if status is not None:
        q.status = status
    if priority is not None:
        q.priority = priority
    if answer_summary is not None:
        q.answer_summary = answer_summary
    db.commit()
    db.refresh(q)
    db.refresh(ko)
    return ko, q


def create_insight(
    db: Session,
    *,
    notebook_id: str,
    statement: str,
    evidence_md: str = "",
    confidence: float = 0.5,
    title: str | None = None,
    supporting_ko_ids: list[str] | None = None,
    answers_question_id: str | None = None,
    vault_path: str | None = None,
    sync_as_reflection: bool = False,
) -> tuple[KnowledgeObject, Insight]:
    title = title or statement[:120]
    ko = _new_ko(
        db,
        notebook_id=notebook_id,
        kind="insight",
        title=title,
        lifecycle_stage="insight",
        workspace_role="resource",
        summary=statement,
        confidence=confidence,
    )
    insight = Insight(
        id=ko.id,
        statement=statement,
        evidence_md=evidence_md,
        confidence=confidence,
        status="active",
    )
    db.add(insight)
    db.commit()
    db.refresh(insight)
    for rid in supporting_ko_ids or []:
        life_svc.create_edge(
            db,
            from_ko_id=ko.id,
            to_ko_id=rid,
            edge_type="supported_by",
            from_type="insight",
            to_type="ko",
            created_by="user",
        )
    if answers_question_id:
        life_svc.create_edge(
            db,
            from_ko_id=ko.id,
            to_ko_id=answers_question_id,
            edge_type="answers",
            from_type="insight",
            to_type="question",
            created_by="user",
        )
        q = db.query(Question).filter(Question.id == answers_question_id).first()
        if q and q.status == "open":
            q.status = "partially_answered"
            db.commit()
    life_cfg = lifecycle_config_dict() or {}
    if vault_path and (
        sync_as_reflection
        or life_cfg.get("sync_insights_to_vault")
    ):
        # Constitution V1.1: mature insights → Research/; reflection-linked → Thinking/
        if sync_as_reflection and not life_cfg.get("sync_insights_to_vault"):
            ko.workspace_role = "thinking"
            ko.graph_eligible = 1
        else:
            ko.workspace_role = "research"
            ko.graph_eligible = 1
        db.commit()
        workspace_svc.sync_note(db, ko, vault_path=vault_path)
    try:
        from . import graph_engine as graph_svc

        graph_svc.maybe_auto_sync(db, notebook_id)
    except Exception:  # noqa: BLE001
        pass
    return ko, insight


def list_questions(
    db: Session,
    *,
    notebook_id: str | None = None,
    status: str | None = "open",
) -> list[tuple[KnowledgeObject, Question]]:
    q = db.query(KnowledgeObject, Question).join(Question, Question.id == KnowledgeObject.id)
    if notebook_id:
        q = q.filter(KnowledgeObject.notebook_id == notebook_id)
    if status:
        q = q.filter(Question.status == status)
    return list(q.order_by(Question.updated_at.desc()).all())


def list_insights(
    db: Session, *, notebook_id: str | None = None
) -> list[tuple[KnowledgeObject, Insight]]:
    q = db.query(KnowledgeObject, Insight).join(Insight, Insight.id == KnowledgeObject.id)
    if notebook_id:
        q = q.filter(KnowledgeObject.notebook_id == notebook_id)
    return list(q.order_by(Insight.updated_at.desc()).all())


def list_reflections(
    db: Session, *, notebook_id: str | None = None
) -> list[tuple[KnowledgeObject, Reflection]]:
    q = db.query(KnowledgeObject, Reflection).join(
        Reflection, Reflection.id == KnowledgeObject.id
    )
    if notebook_id:
        q = q.filter(KnowledgeObject.notebook_id == notebook_id)
    return list(q.order_by(Reflection.updated_at.desc()).all())
