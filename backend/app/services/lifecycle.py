"""Knowledge Lifecycle Engine — transitions, scoring, proposals, history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..db import (
    ConceptProfile,
    ConceptSuggestion,
    Insight,
    KnowledgeObject,
    KoLink,
    LifecycleEvent,
    LifecycleProposal,
    ProjectProfile,
    Question,
    Reflection,
    utcnow,
)
from ..utils import dumps, lifecycle_config_dict, loads, new_id

LIFECYCLE_STAGES = frozenset(
    {
        "signal",
        "resource",
        "knowledge_object",
        "reflection",
        "concept",
        "project",
        "insight",
        "question",
        "discarded",
    }
)

MATURITY_ORDER = ["candidate", "emerging", "stable", "core", "deprecated"]


def cfg() -> dict[str, Any]:
    return lifecycle_config_dict() or {}


def initial_stage_for_connector(connector: str) -> str:
    c = (connector or "").lower()
    skip = {x.lower() for x in (cfg().get("skip_signal_connectors") or ["pubmed", "manual"])}
    if c in skip:
        return "resource"
    signal = {x.lower() for x in (cfg().get("signal_connectors") or [])}
    if c in signal or not skip:
        if c in signal:
            return "signal"
    # Default: resource for unknown scientific-ish, signal for feeds
    if c in {"rss", "web", "wechat", "email"}:
        return "signal"
    return "resource"


def record_event(
    db: Session,
    ko: KnowledgeObject,
    *,
    from_stage: str,
    to_stage: str,
    trigger: str,
    actor: str = "system",
    from_maturity: str = "",
    to_maturity: str = "",
    payload: dict | None = None,
) -> LifecycleEvent:
    ev = LifecycleEvent(
        id=new_id("lev"),
        ko_id=ko.id,
        from_stage=from_stage or "",
        to_stage=to_stage or "",
        from_maturity=from_maturity or "",
        to_maturity=to_maturity or "",
        trigger=trigger,
        actor=actor,
        payload_json=dumps(payload or {}),
    )
    db.add(ev)
    db.commit()
    return ev


def advance(
    db: Session,
    ko: KnowledgeObject,
    to_stage: str,
    *,
    trigger: str,
    actor: str = "system",
    to_maturity: str | None = None,
    payload: dict | None = None,
) -> KnowledgeObject:
    """Apply a lifecycle stage change and append an immutable event."""
    to_stage = (to_stage or "").strip().lower()
    if to_stage not in LIFECYCLE_STAGES:
        raise ValueError(f"invalid lifecycle stage: {to_stage}")
    from_stage = ko.lifecycle_stage or ""
    from_mat = ko.maturity or ""
    new_mat = from_mat
    if to_maturity is not None:
        new_mat = to_maturity
    elif to_stage == "concept" and not new_mat:
        new_mat = "candidate"

    if from_stage == to_stage and (to_maturity is None or from_mat == new_mat):
        return ko

    ko.lifecycle_stage = to_stage
    ko.maturity = new_mat
    ko.lifecycle_updated_at = utcnow()
    if to_stage == "discarded":
        ko.filter_status = "discarded"
        ko.workspace_role = "archived"
        ko.graph_eligible = 0
    db.commit()
    db.refresh(ko)
    record_event(
        db,
        ko,
        from_stage=from_stage,
        to_stage=to_stage,
        from_maturity=from_mat,
        to_maturity=new_mat,
        trigger=trigger,
        actor=actor,
        payload=payload,
    )
    return ko


def keep_signal(
    db: Session,
    ko: KnowledgeObject,
    *,
    actor: str = "system",
) -> KnowledgeObject:
    """signal → resource (Lake write should already have happened or follow)."""
    if (ko.lifecycle_stage or "") != "signal":
        return ko
    ko.filter_status = "kept"
    db.commit()
    return advance(
        db, ko, "resource", trigger="capture", actor=actor, payload={"filter": "kept"}
    )


def mark_analyzed(db: Session, ko: KnowledgeObject, *, confidence: float = 0.0) -> KnowledgeObject:
    """resource (or signal kept) → knowledge_object after AI structure."""
    stage = ko.lifecycle_stage or "resource"
    if stage in {"reflection", "concept", "project", "insight", "question"}:
        # Already past KO structuring
        if confidence:
            ko.confidence = max(float(ko.confidence or 0), confidence)
            db.commit()
        return ko
    if stage == "signal":
        keep_signal(db, ko)
        db.refresh(ko)
    if confidence:
        ko.confidence = confidence
        db.commit()
        db.refresh(ko)
    if (ko.lifecycle_stage or "") != "knowledge_object":
        return advance(
            db,
            ko,
            "knowledge_object",
            trigger="analyze",
            actor="ai",
            payload={"confidence": confidence},
        )
    return ko


def create_edge(
    db: Session,
    *,
    from_ko_id: str,
    to_ko_id: str | None = None,
    to_name: str = "",
    edge_type: str = "related_to",
    from_type: str = "ko",
    to_type: str = "ko",
    weight: float = 1.0,
    evidence: str = "",
    created_by: str = "system",
) -> KoLink:
    link = KoLink(
        id=new_id("kl"),
        from_ko_id=from_ko_id,
        to_ko_id=to_ko_id,
        to_name=to_name or "",
        link_type=edge_type,
        from_type=from_type,
        to_type=to_type,
        weight=weight,
        evidence=evidence,
        created_by=created_by,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def ensure_concept_profile(db: Session, ko: KnowledgeObject) -> ConceptProfile:
    prof = db.query(ConceptProfile).filter(ConceptProfile.ko_id == ko.id).first()
    if prof:
        return prof
    now = utcnow()
    prof = ConceptProfile(
        ko_id=ko.id,
        maturity_level=ko.maturity or "candidate",
        first_seen_at=now,
    )
    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


def ensure_project_profile(db: Session, ko: KnowledgeObject) -> ProjectProfile:
    prof = db.query(ProjectProfile).filter(ProjectProfile.ko_id == ko.id).first()
    if prof:
        return prof
    prof = ProjectProfile(ko_id=ko.id)
    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


def _norm(value: float, ceiling: float) -> float:
    if ceiling <= 0:
        return 0.0
    return max(0.0, min(1.0, float(value) / float(ceiling)))


def recompute_concept_scores(db: Session, ko: KnowledgeObject) -> ConceptProfile:
    """Update concept_profiles.promotion_score and KO evidence_score."""
    prof = ensure_concept_profile(db, ko)
    conf = cfg()
    weights = conf.get("score_weights") or {}
    norms = conf.get("score_norms") or {}

    # Mentions from suggestions matching title
    key = (ko.title or "").strip().lower()
    sug = (
        db.query(ConceptSuggestion)
        .filter(ConceptSuggestion.entity_key == key)
        .order_by(ConceptSuggestion.mention_count.desc())
        .first()
    )
    mention_count = int(sug.mention_count) if sug else int(prof.mention_count or 0)

    reflection_count = (
        db.query(KoLink)
        .filter(
            KoLink.to_ko_id == ko.id,
            KoLink.link_type.in_(("about", "reflects_on", "related_to")),
            KoLink.from_type == "reflection",
        )
        .count()
    )
    # Also count edges from this concept to reflections
    reflection_count += (
        db.query(KoLink)
        .filter(
            KoLink.from_ko_id == ko.id,
            KoLink.to_type == "reflection",
        )
        .count()
    )

    resource_count = (
        db.query(KoLink)
        .filter(
            ((KoLink.to_ko_id == ko.id) | (KoLink.from_ko_id == ko.id)),
            KoLink.link_type.in_(("about", "cites", "derived_from", "related_to")),
        )
        .count()
    )
    # Prefer counting KOs that are resources/knowledge_objects linked about this concept
    project_count = (
        db.query(KoLink)
        .filter(
            ((KoLink.to_ko_id == ko.id) | (KoLink.from_ko_id == ko.id)),
            KoLink.link_type.in_(("member_of", "about", "part_of")),
            ((KoLink.from_type == "project") | (KoLink.to_type == "project")),
        )
        .count()
    )

    first = prof.first_seen_at or ko.created_at or utcnow()
    if first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    persistence_days = max(0, (utcnow() - first).days)
    ai_confidence = float(ko.confidence or prof.ai_confidence or 0)

    prof.mention_count = mention_count
    prof.reflection_count = reflection_count
    prof.resource_count = resource_count
    prof.project_count = project_count
    prof.persistence_days = persistence_days
    prof.ai_confidence = ai_confidence

    score_01 = (
        float(weights.get("mention_count", 0.25))
        * _norm(mention_count, float(norms.get("mention_count", 20)))
        + float(weights.get("reflection_count", 0.25))
        * _norm(reflection_count, float(norms.get("reflection_count", 10)))
        + float(weights.get("resource_count", 0.20))
        * _norm(resource_count, float(norms.get("resource_count", 15)))
        + float(weights.get("project_count", 0.15))
        * _norm(project_count, float(norms.get("project_count", 5)))
        + float(weights.get("persistence_days", 0.10))
        * _norm(persistence_days, float(norms.get("persistence_days", 90)))
        + float(weights.get("ai_confidence", 0.05)) * _norm(ai_confidence, 1.0)
    )
    promotion_score = round(score_01 * 100, 2)
    prof.promotion_score = promotion_score
    ko.evidence_score = score_01
    db.commit()
    db.refresh(prof)
    db.refresh(ko)
    return prof


def recommended_maturity(score: float) -> str:
    th = cfg().get("maturity_thresholds") or {}
    if score >= float(th.get("core", 85)):
        return "core"
    if score >= float(th.get("stable", 65)):
        return "stable"
    if score >= float(th.get("emerging", 40)):
        return "emerging"
    if score >= float(th.get("candidate", 20)):
        return "candidate"
    return "candidate"


def _maturity_index(level: str) -> int:
    try:
        return MATURITY_ORDER.index(level)
    except ValueError:
        return -1


def propose_maturity(
    db: Session,
    ko: KnowledgeObject,
    *,
    reason: str = "",
) -> LifecycleProposal | None:
    """Create a pending proposal if score suggests a higher maturity."""
    if (ko.lifecycle_stage or "") != "concept" and (ko.kind or "") != "concept":
        return None
    prof = recompute_concept_scores(db, ko)
    target = recommended_maturity(prof.promotion_score)
    current = prof.maturity_level or ko.maturity or "candidate"
    if _maturity_index(target) <= _maturity_index(current):
        return None
    # Dedupe pending
    existing = (
        db.query(LifecycleProposal)
        .filter(
            LifecycleProposal.ko_id == ko.id,
            LifecycleProposal.status == "pending",
            LifecycleProposal.proposed_maturity == target,
        )
        .first()
    )
    if existing:
        existing.score = prof.promotion_score
        existing.reason = reason or existing.reason
        db.commit()
        return existing
    prop = LifecycleProposal(
        id=new_id("lpr"),
        ko_id=ko.id,
        notebook_id=ko.notebook_id,
        proposed_stage="concept",
        proposed_maturity=target,
        reason=reason
        or (
            f'Concept "{ko.title}" score {prof.promotion_score:.0f} '
            f"suggests maturity {target} (currently {current})."
        ),
        score=prof.promotion_score,
        status="pending",
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    record_event(
        db,
        ko,
        from_stage=ko.lifecycle_stage or "concept",
        to_stage="concept",
        from_maturity=current,
        to_maturity=target,
        trigger="ai_recommend",
        actor="ai",
        payload={"proposal_id": prop.id, "score": prof.promotion_score},
    )
    return prop


def accept_proposal(
    db: Session,
    proposal: LifecycleProposal,
    *,
    actor: str = "user",
    sync_workspace: bool = False,
    vault_path: str | None = None,
) -> KnowledgeObject:
    ko = db.query(KnowledgeObject).filter(KnowledgeObject.id == proposal.ko_id).first()
    if not ko:
        raise ValueError("Knowledge object not found for proposal")
    to_mat = proposal.proposed_maturity or ""
    to_stage = proposal.proposed_stage or ko.lifecycle_stage or "concept"
    ko = advance(
        db,
        ko,
        to_stage,
        trigger="user_promote",
        actor=actor,
        to_maturity=to_mat,
        payload={"proposal_id": proposal.id, "score": proposal.score},
    )
    if to_stage == "concept":
        prof = ensure_concept_profile(db, ko)
        old = prof.maturity_level
        prof.maturity_level = to_mat or prof.maturity_level
        if to_mat == "stable" and not prof.stable_at:
            prof.stable_at = utcnow()
        if to_mat == "core" and not prof.core_at:
            prof.core_at = utcnow()
        ko.maturity = prof.maturity_level
        ko.kind = "concept"
        ko.lifecycle_stage = "concept"
        db.commit()
        if old != prof.maturity_level:
            pass  # event already recorded by advance
    proposal.status = "accepted"
    db.commit()

    auto = bool(cfg().get("auto_mature"))
    if sync_workspace or (
        to_stage == "concept"
        and (to_mat in {"emerging", "stable", "core"} or ko.workspace_role == "concept")
    ):
        from . import knowledge as knowledge_svc

        if ko.workspace_role != "concept":
            knowledge_svc.promote(
                db, ko, "concept", vault_path=vault_path, sync=bool(vault_path)
            )
        elif vault_path:
            from . import workspace as workspace_svc

            workspace_svc.sync_note(db, ko, vault_path=vault_path)
    elif auto and to_mat in {"emerging", "stable", "core"} and vault_path:
        from . import knowledge as knowledge_svc

        knowledge_svc.promote(db, ko, "concept", vault_path=vault_path, sync=True)

    db.refresh(ko)
    return ko


def dismiss_proposal(db: Session, proposal: LifecycleProposal) -> LifecycleProposal:
    proposal.status = "dismissed"
    db.commit()
    db.refresh(proposal)
    return proposal


def evaluate_workspace(db: Session, notebook_id: str | None = None) -> list[LifecycleProposal]:
    """Recompute scores for concepts and emit maturity proposals."""
    # Expire stale signals first
    expire_signals(db)

    # Optional signal filtering (propose/apply keep heuristics without LLM by default)
    ai_cfg = cfg().get("ai") or {}
    if ai_cfg.get("filter_signals_on_evaluate"):
        from . import lifecycle_ai as life_ai

        sig_q = db.query(KnowledgeObject).filter(
            KnowledgeObject.lifecycle_stage == "signal",
            KnowledgeObject.filter_status.in_(("", "pending")),
        )
        if notebook_id:
            sig_q = sig_q.filter(KnowledgeObject.notebook_id == notebook_id)
        for sig in sig_q.limit(50).all():
            already = (
                db.query(LifecycleEvent)
                .filter(
                    LifecycleEvent.ko_id == sig.id,
                    LifecycleEvent.trigger == "ai_filter",
                )
                .count()
            )
            if already:
                continue
            # Recommend only; do not auto-discard on evaluate (human confirms)
            life_ai.filter_signal(
                db,
                sig,
                apply=False,
                use_llm=bool(ai_cfg.get("use_llm_when_configured")),
            )

    # Refresh project hub scores
    proj_q = db.query(KnowledgeObject).filter(
        (KnowledgeObject.lifecycle_stage == "project")
        | (KnowledgeObject.workspace_role == "project")
    )
    if notebook_id:
        proj_q = proj_q.filter(KnowledgeObject.notebook_id == notebook_id)
    for pko in proj_q.all():
        ensure_project_profile(db, pko)
        try:
            from . import lifecycle_ai as life_ai

            life_ai.project_context_pack(db, pko.id)
        except Exception:  # noqa: BLE001
            pass

    q = db.query(KnowledgeObject).filter(
        (KnowledgeObject.lifecycle_stage == "concept")
        | (KnowledgeObject.kind == "concept")
        | (KnowledgeObject.workspace_role == "concept")
    )
    if notebook_id:
        q = q.filter(KnowledgeObject.notebook_id == notebook_id)
    proposals: list[LifecycleProposal] = []
    for ko in q.all():
        prop = propose_maturity(db, ko)
        if prop:
            proposals.append(prop)
    # Also lift ConceptSuggestions into candidate proposals when score high
    th = float((cfg().get("maturity_thresholds") or {}).get("candidate", 20))
    sug_q = db.query(ConceptSuggestion).filter(ConceptSuggestion.status == "pending")
    if notebook_id:
        sug_q = sug_q.filter(
            (ConceptSuggestion.notebook_id == notebook_id)
            | (ConceptSuggestion.notebook_id.is_(None))
        )
    for sug in sug_q.all():
        # crude score from mentions
        score = min(100.0, float(sug.mention_count) * 5)
        if score < th:
            continue
        # Find or skip if concept exists
        existing = (
            db.query(KnowledgeObject)
            .filter(
                KnowledgeObject.kind == "concept",
                KnowledgeObject.title == sug.entity_name,
            )
            .first()
        )
        if existing:
            continue
        # Proposal without KO yet: store notebook-level proposal with ko_id empty? 
        # Plan requires ko_id FK — create candidate concept KO without vault sync
        if not sug.notebook_id and not notebook_id:
            continue
        nb = sug.notebook_id or notebook_id
        cand = (
            db.query(KnowledgeObject)
            .filter(
                KnowledgeObject.notebook_id == nb,
                KnowledgeObject.kind == "concept",
                KnowledgeObject.title == sug.entity_name,
                KnowledgeObject.maturity == "candidate",
            )
            .first()
        )
        if not cand:
            cand = KnowledgeObject(
                id=new_id("ko"),
                notebook_id=nb,
                kind="concept",
                title=sug.entity_name,
                summary="",
                key_points_json="[]",
                status="ready",
                connector="system",
                content_hash="",
                tags_json="[]",
                entities_json="[]",
                metadata_json=dumps({"from_suggestion_id": sug.id}),
                workspace_role="resource",  # not synced until emerging+accept
                graph_eligible=0,
                lifecycle_stage="concept",
                maturity="candidate",
                confidence=0.3,
                lifecycle_updated_at=utcnow(),
            )
            db.add(cand)
            db.commit()
            db.refresh(cand)
            ensure_concept_profile(db, cand)
            record_event(
                db,
                cand,
                from_stage="",
                to_stage="concept",
                to_maturity="candidate",
                trigger="score_reeval",
                actor="system",
                payload={"suggestion_id": sug.id, "mention_count": sug.mention_count},
            )
        prop = propose_maturity(
            db,
            cand,
            reason=sug.message
            or f'"{sug.entity_name}" appeared {sug.mention_count} times.',
        )
        if prop:
            proposals.append(prop)

    # Keep Graph Engine projection fresh after evaluation
    try:
        from . import graph_engine as graph_svc

        graph_svc.maybe_auto_sync(db, notebook_id)
    except Exception:  # noqa: BLE001
        pass
    return proposals


def list_evolution(db: Session, ko_id: str) -> list[LifecycleEvent]:
    return (
        db.query(LifecycleEvent)
        .filter(LifecycleEvent.ko_id == ko_id)
        .order_by(LifecycleEvent.created_at.asc())
        .all()
    )


def list_proposals(
    db: Session,
    *,
    notebook_id: str | None = None,
    pending_only: bool = True,
) -> list[LifecycleProposal]:
    q = db.query(LifecycleProposal)
    if pending_only:
        q = q.filter(LifecycleProposal.status == "pending")
    if notebook_id:
        q = q.filter(LifecycleProposal.notebook_id == notebook_id)
    return q.order_by(LifecycleProposal.score.desc()).all()


def list_central_concepts(
    db: Session, *, notebook_id: str | None = None, limit: int = 20
) -> list[tuple[KnowledgeObject, ConceptProfile]]:
    q = (
        db.query(KnowledgeObject, ConceptProfile)
        .join(ConceptProfile, ConceptProfile.ko_id == KnowledgeObject.id)
        .filter(KnowledgeObject.lifecycle_stage == "concept")
    )
    if notebook_id:
        q = q.filter(KnowledgeObject.notebook_id == notebook_id)
    rows = q.order_by(ConceptProfile.promotion_score.desc()).limit(limit).all()
    return list(rows)


def list_changes_since(
    db: Session, *, since: datetime, notebook_id: str | None = None, limit: int = 50
) -> list[LifecycleEvent]:
    q = db.query(LifecycleEvent).filter(LifecycleEvent.created_at >= since)
    if notebook_id:
        q = q.join(KnowledgeObject, KnowledgeObject.id == LifecycleEvent.ko_id).filter(
            KnowledgeObject.notebook_id == notebook_id
        )
    return q.order_by(LifecycleEvent.created_at.desc()).limit(limit).all()


def backfill_lifecycle(db: Session) -> dict[str, int]:
    """Migrate existing KOs into lifecycle stages (idempotent-ish)."""
    counts = {"updated": 0, "events": 0, "profiles": 0}
    rows = db.query(KnowledgeObject).all()
    for ko in rows:
        stage = (ko.lifecycle_stage or "").strip()
        role = ko.workspace_role or "resource"
        changed = False
        if not stage or stage == "resource":
            # Infer
            if role == "concept":
                ko.lifecycle_stage = "concept"
                ko.maturity = ko.maturity or "emerging"
                ensure_concept_profile(db, ko)
                counts["profiles"] += 1
                changed = True
            elif role == "reflection":
                ko.lifecycle_stage = "reflection"
                changed = True
            elif role == "project":
                ko.lifecycle_stage = "project"
                ensure_project_profile(db, ko)
                counts["profiles"] += 1
                changed = True
            elif role == "book":
                has_analysis = bool((ko.summary or "").strip() or loads(ko.entities_json, []))
                ko.lifecycle_stage = "knowledge_object" if has_analysis else "resource"
                changed = True
            else:
                has_analysis = bool((ko.summary or "").strip() or loads(ko.entities_json, []))
                new_stage = "knowledge_object" if has_analysis else "resource"
                if ko.lifecycle_stage != new_stage:
                    ko.lifecycle_stage = new_stage
                    changed = True
        if changed:
            ko.lifecycle_updated_at = ko.lifecycle_updated_at or ko.created_at or utcnow()
            counts["updated"] += 1
            # Seed created event if none
            n = (
                db.query(LifecycleEvent)
                .filter(LifecycleEvent.ko_id == ko.id)
                .count()
            )
            if n == 0:
                record_event(
                    db,
                    ko,
                    from_stage="",
                    to_stage=ko.lifecycle_stage,
                    to_maturity=ko.maturity or "",
                    trigger="capture",
                    actor="system",
                    payload={"backfill": True},
                )
                counts["events"] += 1
    db.commit()
    return counts


def expire_signals(db: Session) -> int:
    """Discard expired signals."""
    hours = int(cfg().get("signal_ttl_hours") or 168)
    cutoff = utcnow() - timedelta(hours=hours)
    rows = (
        db.query(KnowledgeObject)
        .filter(
            KnowledgeObject.lifecycle_stage == "signal",
            KnowledgeObject.filter_status.in_(("", "pending")),
        )
        .all()
    )
    n = 0
    for ko in rows:
        created = ko.created_at or utcnow()
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        expires = ko.signal_expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if (expires and expires < utcnow()) or (not expires and created < cutoff):
            advance(db, ko, "discarded", trigger="expire", actor="system")
            n += 1
    return n
