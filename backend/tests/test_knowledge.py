from __future__ import annotations

from app.db import Notebook, SourceDoc
from app.schemas import AnalysisOut
from app.services import knowledge as knowledge_svc
from app.utils import new_id


def test_infer_kind_from_connector():
    assert knowledge_svc.infer_kind("pubmed", {}) == "paper"
    assert knowledge_svc.infer_kind("email", {}) == "newsletter"
    assert knowledge_svc.infer_kind("web", {"source_kind": "article"}) == "article"
    assert knowledge_svc.infer_kind("manual", {"kind": "book"}) == "book"


def test_normalize_filter_tags_no_type_spam():
    tags = knowledge_svc.normalize_filter_tags(
        [
            "AI",
            "type/raw-text",
            "cardiology",
            "paper",
            "important",
            "noise",
            "information",
            "thinking",
            "inbox",
        ],
        max_tags=5,
    )
    assert "paper" not in tags
    assert "raw-text" not in tags
    assert "information" not in tags
    assert "thinking" not in tags
    assert "inbox" not in tags
    assert "ai" in tags or "cardiology" in tags or "important" in tags
    assert len(tags) <= 5


def test_upsert_resource_role(db_session):
    nb = Notebook(id=new_id("nb"), title="t", topic="topic")
    db_session.add(nb)
    src = SourceDoc(
        id=new_id("src"),
        notebook_id=nb.id,
        connector="pubmed",
        title="A Paper",
        url="https://example.com/p",
        authors="Ada",
        raw_text="Full paper text body for lake.",
        content_hash="abc123",
        status="ready",
        metadata_json="{}",
    )
    db_session.add(src)
    db_session.commit()

    ko = knowledge_svc.upsert_from_source(db_session, src)
    assert ko.kind == "paper"
    assert ko.workspace_role == "resource"
    assert ko.graph_eligible == 0
    assert ko.primary_content_uri
    from app.services import content_lake as lake

    assert "Full paper text" in lake.read_text(ko.primary_content_uri)


def test_suggestions_without_concept_files(db_session, vault_path):
    nb = Notebook(id=new_id("nb"), title="t", topic="topic", vault_path=str(vault_path))
    db_session.add(nb)
    db_session.commit()

    # Below threshold — no pending list entry at threshold 5
    knowledge_svc.record_entity_mentions(db_session, ["Migraine"], notebook_id=nb.id)
    assert knowledge_svc.list_concept_suggestions(db_session, notebook_id=nb.id) == []

    for _ in range(5):
        knowledge_svc.record_entity_mentions(db_session, ["Migraine"], notebook_id=nb.id)
    sug = knowledge_svc.list_concept_suggestions(db_session, notebook_id=nb.id)
    assert len(sug) == 1
    assert sug[0].entity_name == "Migraine"
    assert sug[0].mention_count >= 5
    # No Thinking note auto-created from suggestions
    assert not list((vault_path / "Thinking").glob("*.md"))
    assert not list((vault_path / "Concepts").glob("*.md"))


def test_promote_to_concept(db_session, vault_path):
    nb = Notebook(id=new_id("nb"), title="t", topic="topic", vault_path=str(vault_path))
    db_session.add(nb)
    src = SourceDoc(
        id=new_id("src"),
        notebook_id=nb.id,
        connector="web",
        title="Stroke Inflammation",
        raw_text="About stroke.",
        content_hash="h1",
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
            summary="Short summary",
            tags=["medicine", "neurology"],
            key_points=["Point A"],
            entities=["Stroke"],
        ),
    )
    ko = knowledge_svc.promote(
        db_session,
        ko,
        "concept",
        title="Stroke",
        vault_path=str(vault_path),
        sync=True,
    )
    assert ko.workspace_role == "concept"
    assert ko.graph_eligible == 1
    assert ko.vault_path
    note = vault_path / ko.vault_path
    assert note.is_file()
    assert note.parent.name == "Thinking"
    body = note.read_text(encoding="utf-8")
    assert "## Key Ideas" in body
    assert "About stroke." not in body
    assert "Short summary" in body