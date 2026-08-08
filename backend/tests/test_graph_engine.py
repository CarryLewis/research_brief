from __future__ import annotations

from app.db import KnowledgeObject, Notebook
from app.services import graph_engine as graph_svc
from app.services import lifecycle as life_svc
from app.services import thinking as thinking_svc
from app.utils import new_id


def _nb(db):
    nb = Notebook(id=new_id("nb"), title="graph", topic="graph")
    db.add(nb)
    db.commit()
    return nb


def test_sync_hides_signals_and_resources_by_default(db_session):
    nb = _nb(db_session)
    concept = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="concept",
        title="Stroke",
        status="ready",
        connector="manual",
        content_hash="c1",
        workspace_role="resource",
        lifecycle_stage="concept",
        maturity="emerging",
    )
    signal = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="article",
        title="Noise tweet",
        status="ready",
        connector="rss",
        content_hash="s1",
        lifecycle_stage="signal",
        filter_status="pending",
    )
    resource = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="paper",
        title="A paper",
        status="ready",
        connector="pubmed",
        content_hash="r1",
        lifecycle_stage="resource",
        workspace_role="resource",
    )
    db_session.add_all([concept, signal, resource])
    db_session.commit()

    stats = graph_svc.sync_graph(db_session, nb.id)
    assert stats["nodes"] == 2  # concept + resource (resource in projection, hidden by views)
    view = graph_svc.get_view(db_session, "default", notebook_id=nb.id)
    types = {n["node_type"] for n in view["nodes"]}
    assert "concept" in types
    assert "signal" not in types
    assert "resource" not in types

    with_res = graph_svc.get_view(db_session, "with_resources", notebook_id=nb.id)
    assert any(n["node_type"] == "resource" for n in with_res["nodes"])


def test_neighborhood_path_metrics_and_suggest(db_session):
    nb = _nb(db_session)
    c1 = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="concept",
        title="BBB",
        status="ready",
        connector="manual",
        content_hash="bbb",
        lifecycle_stage="concept",
        maturity="stable",
    )
    c2 = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="concept",
        title="Inflammation",
        status="ready",
        connector="manual",
        content_hash="inf",
        lifecycle_stage="concept",
        maturity="emerging",
    )
    proj = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="project",
        title="Stroke Research",
        status="ready",
        connector="manual",
        content_hash="proj",
        lifecycle_stage="project",
        workspace_role="project",
    )
    db_session.add_all([c1, c2, proj])
    db_session.commit()
    life_svc.create_edge(
        db_session,
        from_ko_id=c1.id,
        to_ko_id=c2.id,
        edge_type="supports",
        from_type="concept",
        to_type="concept",
        created_by="user",
    )
    life_svc.create_edge(
        db_session,
        from_ko_id=c1.id,
        to_ko_id=proj.id,
        edge_type="member_of",
        from_type="concept",
        to_type="project",
        created_by="user",
    )

    rko, _ = thinking_svc.create_reflection(
        db_session,
        notebook_id=nb.id,
        title="On BBB and Inflammation",
        body_md="BBB failure relates to Inflammation pathways.",
        related_ko_ids=[c1.id, c2.id],
        sync=False,
    )

    graph_svc.sync_graph(db_session, nb.id)
    nbh = graph_svc.neighborhood(db_session, c1.id, depth=1, notebook_id=nb.id)
    assert any(n["id"] == c2.id for n in nbh["nodes"])

    path = graph_svc.shortest_path(db_session, c2.id, proj.id, notebook_id=nb.id)
    assert path["found"] is True
    assert len(path["path"]) >= 2

    research = graph_svc.get_view(db_session, "research", notebook_id=nb.id)
    assert research["metrics"].get("node_count", 0) >= 3
    assert graph_svc.graph_stats(db_session, notebook_id=nb.id)["nodes"] >= 3

    hist = graph_svc.concept_history(db_session, c1.id)
    assert hist["ko_id"] == c1.id

    tl = graph_svc.timeline(db_session, notebook_id=nb.id)
    assert "frames" in tl

    props = graph_svc.suggest_graph_links(db_session, notebook_id=nb.id)
    assert isinstance(props, list)
    # reflection mentions both concepts — may suggest link or isolated checks
    _ = rko
