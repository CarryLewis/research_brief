from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import KnowledgeObject, Notebook, SourceDoc, utcnow
from app.schemas import AnalysisOut
from app.services import knowledge as knowledge_svc
from app.services import lifecycle as life_svc
from app.services import thinking as thinking_svc
from app.utils import new_id


def _nb(db):
    nb = Notebook(id=new_id("nb"), title="life", topic="life")
    db.add(nb)
    db.commit()
    return nb


def test_capture_pubmed_starts_as_resource(db_session):
    nb = _nb(db_session)
    src = SourceDoc(
        id=new_id("src"),
        notebook_id=nb.id,
        connector="pubmed",
        title="Paper",
        raw_text="Abstract text",
        content_hash="h1",
        status="ready",
        metadata_json="{}",
    )
    db_session.add(src)
    db_session.commit()
    ko = knowledge_svc.upsert_from_source(db_session, src)
    assert ko.lifecycle_stage in {"resource", "knowledge_object"}
    assert ko.primary_content_uri
    events = life_svc.list_evolution(db_session, ko.id)
    assert any(e.trigger == "capture" for e in events)


def test_analyze_advances_to_knowledge_object(db_session):
    nb = _nb(db_session)
    src = SourceDoc(
        id=new_id("src"),
        notebook_id=nb.id,
        connector="pubmed",
        title="Stroke Paper",
        raw_text="About stroke inflammation.",
        content_hash="h2",
        status="ready",
        metadata_json="{}",
    )
    db_session.add(src)
    db_session.commit()
    ko = knowledge_svc.upsert_from_source(db_session, src)
    knowledge_svc.apply_analysis(
        db_session,
        ko,
        AnalysisOut(
            summary="Summary",
            tags=["medicine"],
            key_points=["A"],
            entities=["Stroke", "Inflammation"],
        ),
    )
    db_session.refresh(ko)
    assert ko.lifecycle_stage == "knowledge_object"
    assert ko.confidence > 0


def test_reflection_is_first_class(db_session, vault_path):
    nb = _nb(db_session)
    ko, ref = thinking_svc.create_reflection(
        db_session,
        notebook_id=nb.id,
        title="My stroke thought",
        body_md="I wonder about inflammation pathways.",
        vault_path=str(vault_path),
        sync=True,
    )
    assert ko.lifecycle_stage == "reflection"
    assert ref.body_md.startswith("I wonder")
    assert ko.vault_path
    assert (vault_path / ko.vault_path).is_file()


def test_question_and_insight(db_session):
    nb = _nb(db_session)
    ko_q, q = thinking_svc.create_question(
        db_session,
        notebook_id=nb.id,
        statement="Does inflammation drive stroke recurrence?",
    )
    assert q.status == "open"
    assert ko_q.lifecycle_stage == "question"
    ko_i, ins = thinking_svc.create_insight(
        db_session,
        notebook_id=nb.id,
        statement="Inflammation is a modifiable stroke risk factor.",
        answers_question_id=ko_q.id,
    )
    assert ko_i.lifecycle_stage == "insight"
    assert ins.status == "active"
    db_session.refresh(q)
    assert q.status == "partially_answered"


def test_concept_maturity_proposal(db_session):
    nb = _nb(db_session)
    ko = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="concept",
        title="Stroke",
        summary="",
        status="ready",
        connector="manual",
        content_hash="c1",
        workspace_role="resource",
        lifecycle_stage="concept",
        maturity="candidate",
        confidence=0.8,
        lifecycle_updated_at=utcnow(),
    )
    db_session.add(ko)
    db_session.commit()
    life_svc.ensure_concept_profile(db_session, ko)
    # Inflate mention counts via suggestions
    from app.db import ConceptSuggestion

    db_session.add(
        ConceptSuggestion(
            id=new_id("sug"),
            notebook_id=nb.id,
            entity_name="Stroke",
            entity_key="stroke",
            mention_count=40,
            status="pending",
            message="Stroke appeared 40 times.",
        )
    )
    db_session.commit()
    # Add reflection edges to push score past emerging threshold (40)
    for i in range(8):
        rko, _ = thinking_svc.create_reflection(
            db_session,
            notebook_id=nb.id,
            title=f"Reflection {i}",
            body_md=f"Thinking about stroke {i}",
            related_ko_ids=[ko.id],
            sync=False,
        )
        life_svc.create_edge(
            db_session,
            from_ko_id=rko.id,
            to_ko_id=ko.id,
            edge_type="reflects_on",
            from_type="reflection",
            to_type="concept",
            created_by="user",
        )
    prop = life_svc.propose_maturity(db_session, ko)
    assert prop is not None
    assert prop.proposed_maturity in {"emerging", "stable", "core"}
    assert prop.status == "pending"
    target = prop.proposed_maturity
    accepted = life_svc.accept_proposal(db_session, prop, sync_workspace=False)
    assert accepted.maturity == target
    timeline = life_svc.list_evolution(db_session, ko.id)
    assert any(e.trigger == "user_promote" for e in timeline)


def test_backfill_and_central(db_session):
    nb = _nb(db_session)
    ko = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="paper",
        title="Old paper",
        summary="Has summary",
        status="ready",
        connector="pubmed",
        content_hash="old",
        workspace_role="resource",
        entities_json='["X"]',
    )
    db_session.add(ko)
    db_session.commit()
    stats = life_svc.backfill_lifecycle(db_session)
    assert stats["updated"] >= 1
    db_session.refresh(ko)
    assert ko.lifecycle_stage == "knowledge_object"


def test_signal_filter_and_reflection_assist(db_session):
    from app.services import lifecycle_ai as life_ai

    nb = _nb(db_session)
    sig = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="article",
        title="Clickbait giveaway sponsored post",
        summary="Buy now limited time offer",
        status="ready",
        connector="rss",
        content_hash="sig1",
        workspace_role="resource",
        lifecycle_stage="signal",
        filter_status="pending",
    )
    db_session.add(sig)
    db_session.commit()
    result = life_ai.filter_signal(db_session, sig, apply=True, use_llm=False)
    assert result["decision"] == "discard"
    assert result["applied"] is True
    db_session.refresh(sig)
    assert sig.lifecycle_stage == "discarded"

    keep = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="article",
        title="PubMed stroke clinical trial abstract",
        summary="Nature journal study on migraine",
        status="ready",
        connector="rss",
        content_hash="sig2",
        workspace_role="resource",
        lifecycle_stage="signal",
        filter_status="pending",
    )
    db_session.add(keep)
    db_session.commit()
    kept = life_ai.filter_signal(db_session, keep, apply=True, use_llm=False)
    assert kept["decision"] == "keep"
    db_session.refresh(keep)
    assert keep.lifecycle_stage == "resource"

    rko, ref = thinking_svc.create_reflection(
        db_session,
        notebook_id=nb.id,
        title="Thinking",
        body_md="Stroke inflammation is unclear.\n\nWhat mediates CGRP in migraine?\nHow does aura relate?",
        sync=False,
    )
    assist = life_ai.suggest_questions_from_reflection(
        db_session, rko.id, create=True, use_llm=False
    )
    assert len(assist["questions"]) >= 2
    assert len(assist["created_question_ids"]) >= 2
    db_session.refresh(ref)
    assert "CGRP" in ref.open_questions_json or "migraine" in ref.open_questions_json.lower()


def test_project_context_and_insight_draft(db_session):
    from app.services import lifecycle_ai as life_ai

    nb = _nb(db_session)
    pko = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="project",
        title="Migraine Hub",
        summary="Hub",
        status="ready",
        connector="manual",
        content_hash="proj",
        workspace_role="project",
        lifecycle_stage="project",
        graph_eligible=1,
    )
    cko = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="concept",
        title="CGRP",
        summary="peptide",
        status="ready",
        connector="manual",
        content_hash="cgrp",
        workspace_role="resource",
        lifecycle_stage="concept",
        maturity="emerging",
    )
    db_session.add_all([pko, cko])
    db_session.commit()
    life_svc.ensure_concept_profile(db_session, cko)
    life_svc.create_edge(
        db_session,
        from_ko_id=cko.id,
        to_ko_id=pko.id,
        edge_type="member_of",
        from_type="concept",
        to_type="project",
        created_by="user",
    )
    pack = life_ai.project_context_pack(db_session, pko.id)
    assert pack["knowledge_score"] >= 0
    assert any(c["id"] == cko.id for c in pack["pack"]["concepts"])

    draft = life_ai.draft_insight(
        db_session,
        notebook_id=nb.id,
        supporting_ko_ids=[cko.id],
        use_llm=False,
        accept=True,
    )
    assert draft["accepted"] is True
    assert draft["insight_id"]
