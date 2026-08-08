"""Knowledge Graph Engine — cognitive projection over the Knowledge Database.

Visualization-independent: emits portable JSON (nodes/edges/metrics).
Rebuildable from KO + KoLink + profiles + lifecycle_events.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..db import (
    GraphCommunity,
    GraphEdge,
    GraphMetricsSnapshot,
    GraphNode,
    GraphSyncRun,
    Insight,
    KnowledgeObject,
    KoLink,
    LifecycleEvent,
    LifecycleProposal,
    Question,
    Reflection,
    utcnow,
)
from ..utils import dumps, graph_config_dict, loads, new_id

# Lifecycle KoLink.link_type → canonical graph edge_type
EDGE_ALIASES: dict[str, str] = {
    "inspired_by": "inspired_by",
    "supports": "supports",
    "contradicts": "contradicts",
    "derived_from": "generated_from",
    "answers": "answers",
    "member_of": "belongs_to_project",
    "part_of": "part_of",
    "about": "mentions",
    "related_to": "mentions",
    "related_concept": "mentions",
    "cites": "references",
    "reflects_on": "reflects_on",
    "depends_on": "depends_on",
    "extends": "extends",
    "same_as": "same_as",
    "belongs_to_project": "belongs_to_project",
    "generated_from": "generated_from",
    "mentions": "mentions",
    "references": "references",
}

NEVER_NODE_STAGES = frozenset({"signal", "discarded"})
RESOURCE_STAGES = frozenset({"resource", "knowledge_object"})


def cfg() -> dict[str, Any]:
    return graph_config_dict() or {}


def _norm(value: float, ceiling: float) -> float:
    if ceiling <= 0:
        return 0.0
    return max(0.0, min(1.0, float(value) / float(ceiling)))


def classify_node(ko: KnowledgeObject) -> tuple[str, int] | None:
    """Return (node_type, layer) or None if never shown (signal)."""
    stage = (ko.lifecycle_stage or "").lower()
    role = (ko.workspace_role or "").lower()
    kind = (ko.kind or "").lower()

    if stage in NEVER_NODE_STAGES:
        return None
    if stage == "concept" or role == "concept" or kind == "concept":
        return "concept", 1
    if stage == "reflection" or role == "reflection" or kind == "reflection":
        return "reflection", 2
    if stage == "question" or kind == "question":
        return "question", 3
    if stage == "project" or role == "project" or kind == "project":
        return "project", 4
    if stage == "insight" or kind == "insight":
        return "insight", 5
    if role == "book" or kind == "book":
        return "book", 1  # treat as L1-adjacent; view-gated
    if role == "report" or kind == "report":
        return "report", 6
    if kind == "meeting" or role == "meeting":
        return "meeting", 6
    if stage in RESOURCE_STAGES or role == "resource":
        return "resource", 6
    return "resource", 6


def map_edge_type(
    link_type: str,
    *,
    from_type: str = "",
    to_type: str = "",
) -> str:
    lt = (link_type or "related_to").lower()
    # concept→concept derived_from → extends
    if lt == "derived_from" and from_type == "concept" and to_type == "concept":
        return "extends"
    if lt in {"member_of", "part_of"} and to_type == "project":
        return "belongs_to_project"
    return EDGE_ALIASES.get(lt, "mentions")


def _delete_notebook_projection(db: Session, notebook_id: str | None) -> None:
    nq = db.query(GraphNode)
    eq = db.query(GraphEdge)
    cq = db.query(GraphCommunity)
    if notebook_id:
        nq = nq.filter(GraphNode.notebook_id == notebook_id)
        eq = eq.filter(GraphEdge.notebook_id == notebook_id)
        cq = cq.filter(GraphCommunity.notebook_id == notebook_id)
    nq.delete(synchronize_session=False)
    eq.delete(synchronize_session=False)
    cq.delete(synchronize_session=False)
    db.commit()


def sync_graph(db: Session, notebook_id: str | None = None) -> dict[str, Any]:
    """Rebuild graph projection for a notebook (or all if notebook_id is None)."""
    if notebook_id:
        notebooks = [notebook_id]
    else:
        rows = db.query(KnowledgeObject.notebook_id).distinct().all()
        notebooks = [r[0] for r in rows if r[0]]
        if not notebooks:
            notebooks = [None]

    totals = {"nodes": 0, "edges": 0, "communities": 0, "notebooks": 0}
    for nb in notebooks:
        stats = _sync_one(db, nb)
        totals["nodes"] += stats["nodes"]
        totals["edges"] += stats["edges"]
        totals["communities"] += stats["communities"]
        totals["notebooks"] += 1
    return totals


def _sync_one(db: Session, notebook_id: str | None) -> dict[str, int]:
    _delete_notebook_projection(db, notebook_id)

    q = db.query(KnowledgeObject)
    if notebook_id:
        q = q.filter(KnowledgeObject.notebook_id == notebook_id)
    kos = {ko.id: ko for ko in q.all()}

    node_rows: dict[str, GraphNode] = {}
    for ko in kos.values():
        classified = classify_node(ko)
        if not classified:
            continue
        node_type, layer = classified
        status = ""
        if node_type == "question":
            qq = db.query(Question).filter(Question.id == ko.id).first()
            status = qq.status if qq else ""
        elif node_type == "insight":
            ins = db.query(Insight).filter(Insight.id == ko.id).first()
            status = ins.status if ins else ""
        elif node_type == "reflection":
            ref = db.query(Reflection).filter(Reflection.id == ko.id).first()
            status = ref.status if ref else ""

        node_rows[ko.id] = GraphNode(
            id=ko.id,
            notebook_id=ko.notebook_id,
            node_type=node_type,
            layer=layer,
            label=ko.title or "Untitled",
            maturity=ko.maturity or "",
            weight=0.0,
            degree=0,
            community_id=None,
            status=status,
            lifecycle_stage=ko.lifecycle_stage or "",
            attrs_json=dumps(
                {
                    "confidence": ko.confidence,
                    "evidence_score": ko.evidence_score,
                    "workspace_role": ko.workspace_role,
                    "kind": ko.kind,
                }
            ),
            created_at=ko.created_at,
            updated_at=ko.updated_at,
            last_activity_at=ko.lifecycle_updated_at or ko.updated_at or ko.created_at,
        )

    # Edges: resolved only, both endpoints in projection
    link_q = db.query(KoLink).filter(KoLink.to_ko_id.isnot(None))
    if notebook_id:
        # Restrict to links whose from_ko is in this notebook
        link_q = link_q.filter(KoLink.from_ko_id.in_(list(kos.keys()) or [""]))
    edges: list[GraphEdge] = []
    degree: dict[str, int] = defaultdict(int)
    adj: dict[str, set[str]] = defaultdict(set)
    edge_types_by_node: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for link in link_q.all():
        if not link.to_ko_id:
            continue
        if link.from_ko_id not in node_rows or link.to_ko_id not in node_rows:
            continue
        from_ko = kos.get(link.from_ko_id)
        to_ko = kos.get(link.to_ko_id)
        from_cls = classify_node(from_ko) if from_ko else None
        to_cls = classify_node(to_ko) if to_ko else None
        et = map_edge_type(
            link.link_type,
            from_type=(from_cls[0] if from_cls else link.from_type or ""),
            to_type=(to_cls[0] if to_cls else link.to_type or ""),
        )
        ge = GraphEdge(
            id=new_id("ge"),
            notebook_id=notebook_id or (from_ko.notebook_id if from_ko else None),
            from_id=link.from_ko_id,
            to_id=link.to_ko_id,
            edge_type=et,
            weight=float(link.weight or 1.0),
            evidence=link.evidence or "",
            created_by=link.created_by or "system",
            source_link_id=link.id,
            created_at=link.created_at,
        )
        edges.append(ge)
        degree[link.from_ko_id] += 1
        degree[link.to_ko_id] += 1
        adj[link.from_ko_id].add(link.to_ko_id)
        adj[link.to_ko_id].add(link.from_ko_id)
        edge_types_by_node[link.from_ko_id][et] += 1
        edge_types_by_node[link.to_ko_id][et] += 1

    for nid, node in node_rows.items():
        node.degree = int(degree.get(nid, 0))

    # Communities on concept+project undirected subgraph
    communities = _detect_communities(node_rows, adj)
    for cid, members in communities.items():
        for mid in members:
            if mid in node_rows:
                node_rows[mid].community_id = cid
        # Attach non-backbone nodes to dominant neighbor community
    for nid, node in node_rows.items():
        if node.community_id:
            continue
        votes: dict[str, int] = defaultdict(int)
        for nb in adj.get(nid, ()):
            c = node_rows[nb].community_id if nb in node_rows else None
            if c:
                votes[c] += 1
        if votes:
            node.community_id = max(votes, key=votes.get)

    # Weights
    gcfg = cfg()
    for nid, node in node_rows.items():
        node.weight = _compute_weight(
            node,
            edge_types_by_node.get(nid, {}),
            gcfg,
            kos.get(nid),
        )

    # Persist nodes/edges
    for node in node_rows.values():
        db.add(node)
    for ge in edges:
        db.add(ge)

    # Community rows
    community_meta: list[GraphCommunity] = []
    by_comm: dict[str, list[GraphNode]] = defaultdict(list)
    for node in node_rows.values():
        if node.community_id:
            by_comm[node.community_id].append(node)
    for cid, members in by_comm.items():
        concepts = sorted(
            [m for m in members if m.node_type == "concept"],
            key=lambda m: m.weight,
            reverse=True,
        )
        label = concepts[0].label if concepts else (members[0].label if members else cid)
        community_meta.append(
            GraphCommunity(
                id=cid,
                notebook_id=notebook_id,
                label=label[:200],
                member_count=len(members),
                attrs_json=dumps({"top_concepts": [c.label for c in concepts[:5]]}),
            )
        )
        db.add(community_meta[-1])

    db.commit()

    metrics = _compute_metrics(db, notebook_id, node_rows, edges, gcfg)
    snap = GraphMetricsSnapshot(
        id=new_id("gms"),
        notebook_id=notebook_id,
        metrics_json=dumps(metrics),
    )
    db.add(snap)
    run = GraphSyncRun(
        id=new_id("gsr"),
        notebook_id=notebook_id,
        node_count=len(node_rows),
        edge_count=len(edges),
        community_count=len(community_meta),
        status="ok",
        detail_json=dumps({"metrics_keys": list(metrics.keys())}),
    )
    db.add(run)
    db.commit()

    return {
        "nodes": len(node_rows),
        "edges": len(edges),
        "communities": len(community_meta),
    }


def _detect_communities(
    nodes: dict[str, GraphNode], adj: dict[str, set[str]]
) -> dict[str, set[str]]:
    """Connected components on concept+project subgraph."""
    backbone = {
        nid
        for nid, n in nodes.items()
        if n.node_type in {"concept", "project"}
    }
    seen: set[str] = set()
    communities: dict[str, set[str]] = {}
    for start in backbone:
        if start in seen:
            continue
        comp: set[str] = set()
        dq = deque([start])
        while dq:
            cur = dq.popleft()
            if cur in seen or cur not in backbone:
                continue
            seen.add(cur)
            comp.add(cur)
            for nb in adj.get(cur, ()):
                if nb in backbone and nb not in seen:
                    dq.append(nb)
        if comp:
            communities[new_id("gc")] = comp
    return communities


def _compute_weight(
    node: GraphNode,
    type_counts: dict[str, int],
    gcfg: dict,
    ko: KnowledgeObject | None,
) -> float:
    ww = gcfg.get("weight_weights") or {}
    norms = gcfg.get("weight_norms") or {}
    mat_prior = (gcfg.get("maturity_prior") or {}).get(
        (node.maturity or "").lower(), 0.3
    )

    reflection_deg = type_counts.get("reflects_on", 0)
    project_deg = type_counts.get("belongs_to_project", 0) + type_counts.get("part_of", 0)
    connection_deg = node.degree

    last = node.last_activity_at or utcnow()
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days = max(0, (utcnow() - last).days)
    recency = 1.0 - _norm(days, float(norms.get("recency_days", 90)))

    evidence = 0.0
    if ko:
        evidence = max(float(ko.confidence or 0), float(ko.evidence_score or 0))

    insight_c = 1.0 if node.node_type == "insight" else 0.0
    if node.node_type == "question":
        if node.status == "answered":
            insight_c = 0.0
        elif node.status in {"open", "investigating", "partially_answered"}:
            insight_c = 0.6

    score_01 = (
        float(ww.get("reflection_degree", 0.20))
        * _norm(reflection_deg, float(norms.get("reflection_degree", 10)))
        + float(ww.get("project_degree", 0.15))
        * _norm(project_deg, float(norms.get("project_degree", 5)))
        + float(ww.get("connection_degree", 0.15))
        * _norm(connection_deg, float(norms.get("connection_degree", 20)))
        + float(ww.get("recency", 0.15)) * recency
        + float(ww.get("evidence", 0.15)) * evidence
        + float(ww.get("insight_contribution", 0.10)) * insight_c
        + float(ww.get("maturity_prior", 0.10)) * float(mat_prior)
    )
    weight = 100.0 * score_01
    if node.node_type == "insight":
        weight += float(gcfg.get("insight_base_boost", 15))
    if node.node_type == "question" and node.status in {
        "open",
        "investigating",
        "partially_answered",
    }:
        weight += float(gcfg.get("open_question_boost", 10))
    if node.node_type == "question" and node.status == "answered":
        weight *= float(gcfg.get("answered_question_decay", 0.5))
    return round(min(100.0, max(0.0, weight)), 2)


def _compute_metrics(
    db: Session,
    notebook_id: str | None,
    nodes: dict[str, GraphNode],
    edges: list[GraphEdge],
    gcfg: dict,
) -> dict[str, Any]:
    concepts = [n for n in nodes.values() if n.node_type == "concept"]
    questions = [n for n in nodes.values() if n.node_type == "question"]
    insights = [n for n in nodes.values() if n.node_type == "insight"]
    default_vis = {
        n.id
        for n in nodes.values()
        if n.node_type in {"concept", "project", "question", "insight", "reflection"}
    }

    centrality = sorted(
        [
            {"id": n.id, "label": n.label, "score": round(n.degree * (n.weight / 100.0), 3)}
            for n in concepts
        ],
        key=lambda x: x["score"],
        reverse=True,
    )[:10]

    reflected = set()
    for e in edges:
        if e.edge_type == "reflects_on":
            reflected.add(e.to_id)
            reflected.add(e.from_id)
    concept_ids = {c.id for c in concepts}
    coverage = (
        len(concept_ids & reflected) / len(concept_ids) if concept_ids else 0.0
    )

    answered = sum(1 for q in questions if q.status == "answered")
    q_active = sum(
        1
        for q in questions
        if q.status in {"open", "investigating", "partially_answered", "answered"}
    )
    resolution = answered / q_active if q_active else 0.0

    contradicts = sum(1 for e in edges if e.edge_type == "contradicts")
    conflict = contradicts / len(edges) if edges else 0.0

    orphans = [
        {"id": n.id, "label": n.label, "node_type": n.node_type}
        for n in nodes.values()
        if n.id in default_vis and n.degree == 0
    ]

    emerging = [n for n in concepts if n.maturity == "emerging"]
    window = int(gcfg.get("metrics_window_days") or 30)
    since = utcnow() - timedelta(days=window)
    insight_recent = sum(
        1
        for n in insights
        if n.created_at
        and (
            n.created_at.replace(tzinfo=timezone.utc)
            if n.created_at.tzinfo is None
            else n.created_at
        )
        >= since
    )
    insight_rate = insight_recent / float(window)

    # Project density: average clustering among project member sets
    project_ids = [n.id for n in nodes.values() if n.node_type == "project"]
    densities = []
    for pid in project_ids:
        members = {
            e.from_id if e.to_id == pid else e.to_id
            for e in edges
            if e.edge_type in {"belongs_to_project", "part_of", "mentions"}
            and (e.from_id == pid or e.to_id == pid)
        }
        members.discard(pid)
        m = len(members)
        if m < 2:
            densities.append(0.0)
            continue
        member_edges = sum(
            1
            for e in edges
            if e.from_id in members and e.to_id in members
        )
        possible = m * (m - 1) / 2
        densities.append(member_edges / possible if possible else 0.0)
    project_density = sum(densities) / len(densities) if densities else 0.0

    prev = (
        db.query(GraphMetricsSnapshot)
        .filter(GraphMetricsSnapshot.notebook_id == notebook_id)
        .order_by(GraphMetricsSnapshot.created_at.desc())
        .first()
    )
    growth = {"nodes_delta": len(nodes), "edges_delta": len(edges)}
    if prev:
        old = loads(prev.metrics_json, {}) or {}
        growth = {
            "nodes_delta": len(nodes) - int(old.get("node_count") or 0),
            "edges_delta": len(edges) - int(old.get("edge_count") or 0),
        }

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "concept_centrality": centrality,
        "project_density": round(project_density, 4),
        "reflection_coverage": round(coverage, 4),
        "question_resolution_rate": round(resolution, 4),
        "knowledge_growth": growth,
        "emerging_concepts": [
            {"id": n.id, "label": n.label, "weight": n.weight} for n in emerging
        ],
        "orphan_nodes": orphans[:50],
        "conflict_density": round(conflict, 4),
        "insight_production_rate": round(insight_rate, 4),
    }


def maybe_auto_sync(db: Session, notebook_id: str | None) -> None:
    if not (cfg().get("auto_sync_on_mutate", True)):
        return
    if not notebook_id:
        return
    try:
        sync_graph(db, notebook_id)
    except Exception:  # noqa: BLE001
        pass


def _node_out(n: GraphNode) -> dict[str, Any]:
    return {
        "id": n.id,
        "node_type": n.node_type,
        "layer": n.layer,
        "label": n.label,
        "weight": n.weight,
        "maturity": n.maturity,
        "degree": n.degree,
        "community_id": n.community_id,
        "status": n.status,
        "lifecycle_stage": n.lifecycle_stage,
        "attrs": loads(n.attrs_json, {}) or {},
    }


def _edge_out(e: GraphEdge) -> dict[str, Any]:
    return {
        "id": e.id,
        "from": e.from_id,
        "to": e.to_id,
        "edge_type": e.edge_type,
        "weight": e.weight,
    }


def get_view(
    db: Session,
    view_id: str,
    *,
    notebook_id: str | None = None,
    fresh: bool = False,
) -> dict[str, Any]:
    if fresh:
        sync_graph(db, notebook_id)

    views = cfg().get("views") or {}
    view_cfg = views.get(view_id) or views.get("default") or {
        "node_types": ["concept", "project", "question", "insight"]
    }
    allowed = set(view_cfg.get("node_types") or [])
    refl_min = int(view_cfg.get("reflection_min_degree") or 0)

    nq = db.query(GraphNode)
    eq = db.query(GraphEdge)
    cq = db.query(GraphCommunity)
    if notebook_id:
        nq = nq.filter(GraphNode.notebook_id == notebook_id)
        eq = eq.filter(GraphEdge.notebook_id == notebook_id)
        cq = cq.filter(GraphCommunity.notebook_id == notebook_id)

    nodes = []
    node_ids: set[str] = set()
    for n in nq.all():
        if n.node_type not in allowed:
            continue
        if view_id == "default" and n.node_type == "reflection" and n.degree < refl_min:
            continue
        if view_id == "governance":
            # orphans, emerging, conflict endpoints filled below — include all allowed first
            pass
        nodes.append(n)
        node_ids.add(n.id)

    if view_id == "governance":
        # Prefer orphans + emerging + contradict endpoints
        metrics = get_metrics(db, notebook_id=notebook_id)
        focus = {o["id"] for o in metrics.get("orphan_nodes") or []}
        focus |= {e["id"] for e in metrics.get("emerging_concepts") or []}
        for e in eq.all():
            if e.edge_type == "contradicts":
                focus.add(e.from_id)
                focus.add(e.to_id)
        if focus:
            nodes = [n for n in nodes if n.id in focus or n.node_type == "concept"]
            node_ids = {n.id for n in nodes}

    edges = [
        e
        for e in eq.all()
        if e.from_id in node_ids and e.to_id in node_ids
    ]

    communities = []
    for c in cq.all():
        communities.append(
            {"id": c.id, "label": c.label, "size": c.member_count}
        )

    metrics = get_metrics(db, notebook_id=notebook_id)
    return {
        "view": view_id,
        "notebook_id": notebook_id,
        "nodes": [_node_out(n) for n in nodes],
        "edges": [_edge_out(e) for e in edges],
        "communities": communities,
        "metrics": metrics,
        "generated_at": utcnow().isoformat(),
    }


def neighborhood(
    db: Session,
    ko_id: str,
    *,
    depth: int = 1,
    notebook_id: str | None = None,
    fresh: bool = False,
) -> dict[str, Any]:
    if fresh:
        sync_graph(db, notebook_id)
    depth = max(1, min(depth, 4))
    seed = db.query(GraphNode).filter(GraphNode.id == ko_id).first()
    if not seed:
        raise ValueError("Node not in graph projection (sync first?)")

    eq = db.query(GraphEdge)
    if notebook_id:
        eq = eq.filter(GraphEdge.notebook_id == notebook_id)
    all_edges = eq.all()
    adj: dict[str, set[str]] = defaultdict(set)
    edge_map: list[GraphEdge] = []
    for e in all_edges:
        adj[e.from_id].add(e.to_id)
        adj[e.to_id].add(e.from_id)
        edge_map.append(e)

    seen = {ko_id}
    frontier = {ko_id}
    for _ in range(depth):
        nxt: set[str] = set()
        for u in frontier:
            for v in adj.get(u, ()):
                if v not in seen:
                    nxt.add(v)
        seen |= nxt
        frontier = nxt

    nq = db.query(GraphNode).filter(GraphNode.id.in_(list(seen)))
    nodes = nq.all()
    node_ids = {n.id for n in nodes}
    edges = [e for e in edge_map if e.from_id in node_ids and e.to_id in node_ids]
    return {
        "ko_id": ko_id,
        "depth": depth,
        "nodes": [_node_out(n) for n in nodes],
        "edges": [_edge_out(e) for e in edges],
        "generated_at": utcnow().isoformat(),
    }


def shortest_path(
    db: Session,
    from_id: str,
    to_id: str,
    *,
    notebook_id: str | None = None,
) -> dict[str, Any]:
    eq = db.query(GraphEdge)
    if notebook_id:
        eq = eq.filter(GraphEdge.notebook_id == notebook_id)
    adj: dict[str, list[str]] = defaultdict(list)
    for e in eq.all():
        adj[e.from_id].append(e.to_id)
        adj[e.to_id].append(e.from_id)

    if from_id not in adj and from_id != to_id:
        # may still be isolated node
        pass
    prev: dict[str, str | None] = {from_id: None}
    dq = deque([from_id])
    found = False
    while dq:
        cur = dq.popleft()
        if cur == to_id:
            found = True
            break
        for nb in adj.get(cur, []):
            if nb not in prev:
                prev[nb] = cur
                dq.append(nb)
    if not found and from_id != to_id:
        return {"from": from_id, "to": to_id, "path": [], "found": False}
    path = []
    cur: str | None = to_id
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
        if cur is None and path[-1] != from_id:
            break
    path.reverse()
    if path and path[0] != from_id:
        return {"from": from_id, "to": to_id, "path": [], "found": False}
    nodes = db.query(GraphNode).filter(GraphNode.id.in_(path)).all()
    by_id = {n.id: n for n in nodes}
    return {
        "from": from_id,
        "to": to_id,
        "found": True,
        "path": [_node_out(by_id[i]) for i in path if i in by_id],
    }


def concept_history(db: Session, ko_id: str) -> dict[str, Any]:
    events = (
        db.query(LifecycleEvent)
        .filter(LifecycleEvent.ko_id == ko_id)
        .order_by(LifecycleEvent.created_at.asc())
        .all()
    )
    edges = (
        db.query(GraphEdge)
        .filter((GraphEdge.from_id == ko_id) | (GraphEdge.to_id == ko_id))
        .order_by(GraphEdge.created_at.asc())
        .all()
    )
    node = db.query(GraphNode).filter(GraphNode.id == ko_id).first()
    return {
        "ko_id": ko_id,
        "node": _node_out(node) if node else None,
        "lifecycle_events": [
            {
                "id": e.id,
                "from_stage": e.from_stage,
                "to_stage": e.to_stage,
                "from_maturity": e.from_maturity,
                "to_maturity": e.to_maturity,
                "trigger": e.trigger,
                "actor": e.actor,
                "payload": loads(e.payload_json, {}) or {},
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "edges": [_edge_out(e) for e in edges],
    }


def project_graph(db: Session, project_id: str, *, fresh: bool = False) -> dict[str, Any]:
    node = db.query(GraphNode).filter(GraphNode.id == project_id).first()
    if not node:
        raise ValueError("Project not in graph projection")
    if fresh:
        sync_graph(db, node.notebook_id)
    return neighborhood(db, project_id, depth=2, notebook_id=node.notebook_id)


def timeline(
    db: Session,
    *,
    since: datetime | None = None,
    notebook_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    since = since or (utcnow() - timedelta(days=30))
    q = db.query(LifecycleEvent).filter(LifecycleEvent.created_at >= since)
    if notebook_id:
        q = q.join(KnowledgeObject, KnowledgeObject.id == LifecycleEvent.ko_id).filter(
            KnowledgeObject.notebook_id == notebook_id
        )
    events = q.order_by(LifecycleEvent.created_at.asc()).limit(limit).all()
    frames = []
    for e in events:
        frames.append(
            {
                "at": e.created_at.isoformat() if e.created_at else None,
                "ko_id": e.ko_id,
                "from_stage": e.from_stage,
                "to_stage": e.to_stage,
                "from_maturity": e.from_maturity,
                "to_maturity": e.to_maturity,
                "trigger": e.trigger,
                "actor": e.actor,
            }
        )
    return {
        "since": since.isoformat(),
        "notebook_id": notebook_id,
        "frames": frames,
        "count": len(frames),
    }


def open_questions_graph(
    db: Session, *, notebook_id: str | None = None
) -> dict[str, Any]:
    nq = db.query(GraphNode).filter(
        GraphNode.node_type == "question",
        GraphNode.status.in_(("open", "investigating", "partially_answered")),
    )
    if notebook_id:
        nq = nq.filter(GraphNode.notebook_id == notebook_id)
    questions = nq.all()
    ids = {q.id for q in questions}
    # include neighbors
    eq = db.query(GraphEdge)
    if notebook_id:
        eq = eq.filter(GraphEdge.notebook_id == notebook_id)
    neighbor_ids = set(ids)
    edges = []
    for e in eq.all():
        if e.from_id in ids or e.to_id in ids:
            edges.append(e)
            neighbor_ids.add(e.from_id)
            neighbor_ids.add(e.to_id)
    nodes = db.query(GraphNode).filter(GraphNode.id.in_(list(neighbor_ids) or [""])).all()
    return {
        "nodes": [_node_out(n) for n in nodes],
        "edges": [_edge_out(e) for e in edges],
        "open_count": len(questions),
    }


def get_metrics(
    db: Session, *, notebook_id: str | None = None, series: bool = False
) -> dict[str, Any]:
    q = db.query(GraphMetricsSnapshot)
    if notebook_id:
        q = q.filter(GraphMetricsSnapshot.notebook_id == notebook_id)
    latest = q.order_by(GraphMetricsSnapshot.created_at.desc()).first()
    if not latest:
        return {}
    data = loads(latest.metrics_json, {}) or {}
    if not series:
        return data
    rows = q.order_by(GraphMetricsSnapshot.created_at.asc()).limit(50).all()
    return {
        "latest": data,
        "series": [
            {
                "at": r.created_at.isoformat() if r.created_at else None,
                "metrics": loads(r.metrics_json, {}) or {},
            }
            for r in rows
        ],
    }


def graph_stats(db: Session, *, notebook_id: str | None = None) -> dict[str, Any]:
    nq = db.query(GraphNode)
    eq = db.query(GraphEdge)
    if notebook_id:
        nq = nq.filter(GraphNode.notebook_id == notebook_id)
        eq = eq.filter(GraphEdge.notebook_id == notebook_id)
    by_type: dict[str, int] = defaultdict(int)
    by_layer: dict[int, int] = defaultdict(int)
    for n in nq.all():
        by_type[n.node_type] += 1
        by_layer[n.layer] += 1
    return {
        "notebook_id": notebook_id,
        "nodes": sum(by_type.values()),
        "edges": eq.count(),
        "by_type": dict(by_type),
        "by_layer": {str(k): v for k, v in by_layer.items()},
    }


def list_orphans(
    db: Session, *, notebook_id: str | None = None
) -> list[dict[str, Any]]:
    metrics = get_metrics(db, notebook_id=notebook_id)
    return list(metrics.get("orphan_nodes") or [])


def suggest_graph_links(
    db: Session,
    *,
    notebook_id: str,
    use_llm: bool = False,
) -> list[dict[str, Any]]:
    """Propose missing concept links from co-occurrence in reflections; propose-only."""
    reflections = (
        db.query(KnowledgeObject)
        .filter(
            KnowledgeObject.notebook_id == notebook_id,
            KnowledgeObject.lifecycle_stage == "reflection",
        )
        .all()
    )
    concepts = (
        db.query(GraphNode)
        .filter(
            GraphNode.notebook_id == notebook_id,
            GraphNode.node_type == "concept",
        )
        .all()
    )
    concept_by_label = {c.label.lower(): c for c in concepts if c.label}

    # Existing edges between concepts
    existing: set[tuple[str, str]] = set()
    for e in db.query(GraphEdge).filter(GraphEdge.notebook_id == notebook_id).all():
        a, b = sorted([e.from_id, e.to_id])
        existing.add((a, b))

    proposals: list[dict[str, Any]] = []
    for ref in reflections:
        text = f"{ref.title} {ref.summary}".lower()
        hit = [c for label, c in concept_by_label.items() if label in text]
        for i in range(len(hit)):
            for j in range(i + 1, len(hit)):
                a, b = sorted([hit[i].id, hit[j].id])
                if (a, b) in existing:
                    continue
                key = (a, b)
                existing.add(key)
                reason = (
                    f'Co-mentioned in reflection "{ref.title}": '
                    f"{hit[i].label} ↔ {hit[j].label}"
                )
                prop = LifecycleProposal(
                    id=new_id("lpr"),
                    ko_id=hit[i].id,
                    notebook_id=notebook_id,
                    proposed_stage="",
                    proposed_maturity="",
                    reason=reason,
                    score=40.0,
                    status="pending",
                    payload_json=dumps(
                        {
                            "graph_action": "suggest_link",
                            "from_id": hit[i].id,
                            "to_id": hit[j].id,
                            "edge_type": "mentions",
                            "reflection_id": ref.id,
                        }
                    ),
                )
                db.add(prop)
                proposals.append(
                    {
                        "proposal_id": prop.id,
                        "from_id": hit[i].id,
                        "to_id": hit[j].id,
                        "reason": reason,
                    }
                )

    # Duplicate concepts by normalized title
    by_key: dict[str, list[GraphNode]] = defaultdict(list)
    for c in concepts:
        key = "".join(ch for ch in (c.label or "").lower() if ch.isalnum())
        if key:
            by_key[key].append(c)
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        primary = group[0]
        for other in group[1:]:
            prop = LifecycleProposal(
                id=new_id("lpr"),
                ko_id=primary.id,
                notebook_id=notebook_id,
                proposed_stage="",
                proposed_maturity="",
                reason=f'Duplicate concept titles: "{primary.label}" ~ "{other.label}"',
                score=55.0,
                status="pending",
                payload_json=dumps(
                    {
                        "graph_action": "same_as",
                        "from_id": primary.id,
                        "to_id": other.id,
                        "edge_type": "same_as",
                    }
                ),
            )
            db.add(prop)
            proposals.append(
                {
                    "proposal_id": prop.id,
                    "from_id": primary.id,
                    "to_id": other.id,
                    "reason": prop.reason,
                    "action": "same_as",
                }
            )

    # Isolated reflections
    for ref in reflections:
        gn = db.query(GraphNode).filter(GraphNode.id == ref.id).first()
        if gn and gn.degree == 0:
            prop = LifecycleProposal(
                id=new_id("lpr"),
                ko_id=ref.id,
                notebook_id=notebook_id,
                proposed_stage="",
                proposed_maturity="",
                reason=f'Isolated reflection "{ref.title}" has no concept links',
                score=30.0,
                status="pending",
                payload_json=dumps(
                    {"graph_action": "link_reflection", "reflection_id": ref.id}
                ),
            )
            db.add(prop)
            proposals.append(
                {
                    "proposal_id": prop.id,
                    "reflection_id": ref.id,
                    "reason": prop.reason,
                    "action": "link_reflection",
                }
            )

    db.commit()
    _ = use_llm  # reserved for future LLM enrichment
    return proposals
