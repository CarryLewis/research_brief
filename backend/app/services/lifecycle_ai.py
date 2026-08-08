"""Lifecycle-aware AI decision points.

Heuristic baselines always work; LLM enrichments run when configured.
Every AI/system decision that mutates state logs a lifecycle_events row.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from ..db import KnowledgeObject, KoLink, Question, Reflection
from ..utils import dumps, lifecycle_config_dict, loads
from . import llm as llm_svc
from . import lifecycle as life_svc
from . import thinking as thinking_svc

# Cheap keep signals for scientific / research noise filter
_KEEP_HINTS = re.compile(
    r"\b(doi|pubmed|arxiv|clinical|trial|stroke|migraine|paper|study|abstract|"
    r"hypothesis|framework|research|journal|nature|lancet|nejm)\b",
    re.I,
)
_DISCARD_HINTS = re.compile(
    r"\b(clickbait|giveaway|unsubscribe|crypto airdrop|sponsored post|"
    r"limited time offer|buy now)\b",
    re.I,
)


def cfg() -> dict[str, Any]:
    return lifecycle_config_dict() or {}


def filter_signal(
    db: Session,
    ko: KnowledgeObject,
    *,
    apply: bool = False,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Signal stage: recommend keep vs discard. Optionally apply."""
    if (ko.lifecycle_stage or "") != "signal":
        return {
            "ko_id": ko.id,
            "decision": "skip",
            "reason": f"not a signal (stage={ko.lifecycle_stage})",
            "applied": False,
        }

    text = " ".join(
        [
            ko.title or "",
            ko.summary or "",
            " ".join(loads(ko.tags_json, []) or []),
            " ".join(loads(ko.entities_json, []) or []),
        ]
    )
    decision = "keep"
    reason = "default keep for unknown signal"
    confidence = 0.4
    actor = "system"

    if _DISCARD_HINTS.search(text):
        decision = "discard"
        reason = "matched discard heuristics"
        confidence = 0.7
    elif _KEEP_HINTS.search(text):
        decision = "keep"
        reason = "matched research/keep heuristics"
        confidence = 0.75

    if use_llm and llm_svc.is_configured():
        try:
            data = llm_svc.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "You filter ephemeral research signals. "
                            "Return JSON: keep (bool), reason (string), "
                            "importance_prior (float 0-1)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Connector: {ko.connector}\n"
                            f"Title: {ko.title}\n"
                            f"Summary: {(ko.summary or '')[:1500]}\n"
                            f"Tags: {loads(ko.tags_json, [])}"
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=300,
            )
            decision = "keep" if data.get("keep") else "discard"
            reason = str(data.get("reason") or reason)[:500]
            confidence = float(data.get("importance_prior") or confidence)
            actor = "ai"
        except Exception as exc:  # noqa: BLE001
            reason = f"{reason}; llm_fallback: {exc}"[:500]

    life_svc.record_event(
        db,
        ko,
        from_stage="signal",
        to_stage="signal",
        trigger="ai_filter" if actor == "ai" else "score_reeval",
        actor=actor,
        payload={
            "decision": decision,
            "reason": reason,
            "confidence": confidence,
            "applied": False,
        },
    )

    applied = False
    if apply:
        if decision == "keep":
            life_svc.keep_signal(db, ko, actor=actor)
            applied = True
        else:
            life_svc.advance(
                db,
                ko,
                "discarded",
                trigger="ai_recommend" if actor == "ai" else "expire",
                actor=actor,
                payload={"reason": reason, "confidence": confidence},
            )
            applied = True
        # Update last event payload applied flag via new event already recorded by advance

    return {
        "ko_id": ko.id,
        "decision": decision,
        "reason": reason,
        "confidence": confidence,
        "applied": applied,
        "actor": actor,
    }


def suggest_questions_from_reflection(
    db: Session,
    reflection_id: str,
    *,
    create: bool = False,
    use_llm: bool = True,
    max_questions: int = 5,
) -> dict[str, Any]:
    """Reflection assist: suggest open research questions; optionally create Question rows."""
    ref = db.query(Reflection).filter(Reflection.id == reflection_id).first()
    ko = db.query(KnowledgeObject).filter(KnowledgeObject.id == reflection_id).first()
    if not ref or not ko:
        raise ValueError("Reflection not found")

    body = ref.body_md or ""
    suggested: list[str] = []

    # Heuristic: lines / sentences ending with ?
    for line in body.splitlines():
        line = line.strip().lstrip("-* ").strip()
        if line.endswith("?") and 8 <= len(line) <= 240:
            suggested.append(line)
    for q in loads(ref.open_questions_json, []) or []:
        if isinstance(q, str) and q.strip():
            suggested.append(q.strip())

    actor = "system"
    if use_llm and llm_svc.is_configured() and body.strip():
        try:
            data = llm_svc.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Extract unresolved research questions from a reflection. "
                            "Return JSON: questions (string array, max 5)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Title: {ko.title}\n\n{body[:6000]}",
                    },
                ],
                temperature=0.2,
                max_tokens=600,
            )
            for q in data.get("questions") or []:
                if isinstance(q, str) and q.strip():
                    suggested.append(q.strip())
            actor = "ai"
        except Exception:  # noqa: BLE001
            pass

    # Dedupe preserve order
    seen: set[str] = set()
    unique: list[str] = []
    for q in suggested:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(q)
        if len(unique) >= max_questions:
            break

    ref.open_questions_json = dumps(unique)
    db.commit()

    life_svc.record_event(
        db,
        ko,
        from_stage="reflection",
        to_stage="reflection",
        trigger="ai_recommend" if actor == "ai" else "score_reeval",
        actor=actor,
        payload={"suggested_questions": unique, "create": create},
    )

    created_ids: list[str] = []
    if create:
        for statement in unique:
            qko, _ = thinking_svc.create_question(
                db,
                notebook_id=ko.notebook_id or "",
                statement=statement,
                related_ko_ids=[ko.id],
            )
            created_ids.append(qko.id)

    # Link suggestions to existing concepts/projects by title overlap
    link_suggestions = suggest_links_for_reflection(db, ko)

    return {
        "reflection_id": reflection_id,
        "questions": unique,
        "created_question_ids": created_ids,
        "link_suggestions": link_suggestions,
        "actor": actor,
    }


def suggest_links_for_reflection(db: Session, reflection_ko: KnowledgeObject) -> list[dict]:
    """Suggest links only to existing Concepts/Projects (Constitution curation)."""
    nb = reflection_ko.notebook_id
    text = f"{reflection_ko.title} {reflection_ko.summary}".lower()
    q = db.query(KnowledgeObject).filter(
        KnowledgeObject.lifecycle_stage.in_(("concept", "project")),
    )
    if nb:
        q = q.filter(KnowledgeObject.notebook_id == nb)
    out: list[dict] = []
    for cand in q.all():
        title = (cand.title or "").strip()
        if len(title) < 3:
            continue
        if title.lower() in text:
            out.append(
                {
                    "ko_id": cand.id,
                    "title": title,
                    "stage": cand.lifecycle_stage,
                    "reason": "title mentioned in reflection",
                }
            )
    return out[:12]


def project_context_pack(db: Session, project_id: str) -> dict[str, Any]:
    """Project retrieve: linked concepts, questions, insights, reflections, resources."""
    ko = db.query(KnowledgeObject).filter(KnowledgeObject.id == project_id).first()
    if not ko:
        raise ValueError("Project not found")
    life_svc.ensure_project_profile(db, ko)
    links = (
        db.query(KoLink)
        .filter((KoLink.from_ko_id == project_id) | (KoLink.to_ko_id == project_id))
        .all()
    )
    related_ids = set()
    for link in links:
        if link.from_ko_id != project_id:
            related_ids.add(link.from_ko_id)
        if link.to_ko_id and link.to_ko_id != project_id:
            related_ids.add(link.to_ko_id)

    buckets: dict[str, list[dict]] = {
        "concepts": [],
        "questions": [],
        "insights": [],
        "reflections": [],
        "resources": [],
        "other": [],
    }
    for rid in related_ids:
        rko = db.query(KnowledgeObject).filter(KnowledgeObject.id == rid).first()
        if not rko:
            continue
        item = {
            "id": rko.id,
            "title": rko.title,
            "stage": rko.lifecycle_stage,
            "maturity": rko.maturity or "",
            "summary": (rko.summary or "")[:300],
        }
        stage = rko.lifecycle_stage or ""
        if stage == "concept" or rko.kind == "concept":
            buckets["concepts"].append(item)
        elif stage == "question" or rko.kind == "question":
            buckets["questions"].append(item)
        elif stage == "insight" or rko.kind == "insight":
            buckets["insights"].append(item)
        elif stage == "reflection" or rko.kind == "reflection":
            buckets["reflections"].append(item)
        elif stage in {"resource", "knowledge_object"}:
            buckets["resources"].append(item)
        else:
            buckets["other"].append(item)

    open_q = (
        db.query(Question)
        .join(KnowledgeObject, KnowledgeObject.id == Question.id)
        .filter(
            KnowledgeObject.notebook_id == ko.notebook_id,
            Question.status.in_(("open", "investigating", "partially_answered")),
        )
        .count()
        if ko.notebook_id
        else 0
    )
    prof = life_svc.ensure_project_profile(db, ko)
    concept_score = 0.0
    for c in buckets["concepts"]:
        cko = db.query(KnowledgeObject).filter(KnowledgeObject.id == c["id"]).first()
        if cko:
            from ..db import ConceptProfile

            cp = db.query(ConceptProfile).filter(ConceptProfile.ko_id == cko.id).first()
            concept_score += float(cp.promotion_score) if cp else 10.0
    prof.knowledge_score = concept_score + 15.0 * len(buckets["insights"])
    prof.active_question_count = open_q
    db.commit()

    life_svc.record_event(
        db,
        ko,
        from_stage=ko.lifecycle_stage or "project",
        to_stage=ko.lifecycle_stage or "project",
        trigger="score_reeval",
        actor="system",
        payload={
            "knowledge_score": prof.knowledge_score,
            "counts": {k: len(v) for k, v in buckets.items()},
        },
    )

    return {
        "project_id": project_id,
        "title": ko.title,
        "knowledge_score": prof.knowledge_score,
        "active_question_count": prof.active_question_count,
        "pack": buckets,
    }


def draft_insight(
    db: Session,
    *,
    notebook_id: str,
    supporting_ko_ids: list[str] | None = None,
    question_id: str | None = None,
    use_llm: bool = True,
    accept: bool = False,
) -> dict[str, Any]:
    """Insight synthesize: draft statement + evidence; user must accept to persist (default)."""
    supporting_ko_ids = supporting_ko_ids or []
    snippets: list[str] = []
    for kid in supporting_ko_ids:
        sko = db.query(KnowledgeObject).filter(KnowledgeObject.id == kid).first()
        if sko:
            snippets.append(f"- [{sko.lifecycle_stage}] {sko.title}: {(sko.summary or '')[:400]}")
    q_text = ""
    if question_id:
        q = db.query(Question).filter(Question.id == question_id).first()
        qko = db.query(KnowledgeObject).filter(KnowledgeObject.id == question_id).first()
        if q:
            q_text = q.statement
        elif qko:
            q_text = qko.title

    statement = ""
    evidence_md = "\n".join(snippets)
    confidence = 0.4
    actor = "system"

    if use_llm and llm_svc.is_configured():
        try:
            data = llm_svc.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Synthesize a research insight. Return JSON: "
                            "statement (string), evidence_md (string), confidence (0-1)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Open question: {q_text}\n\n"
                            f"Supporting material:\n{evidence_md or '(none)'}"
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=800,
            )
            statement = str(data.get("statement") or "").strip()
            evidence_md = str(data.get("evidence_md") or evidence_md)
            confidence = float(data.get("confidence") or confidence)
            actor = "ai"
        except Exception as exc:  # noqa: BLE001
            statement = f"Draft insight pending review ({exc})"[:200]

    if not statement:
        if q_text:
            statement = f"Working answer toward: {q_text}"
        elif snippets:
            statement = "Emerging pattern across linked materials (draft)"
        else:
            statement = "Untitled insight draft"

    draft = {
        "statement": statement,
        "evidence_md": evidence_md,
        "confidence": confidence,
        "supporting_ko_ids": supporting_ko_ids,
        "answers_question_id": question_id,
        "actor": actor,
        "accepted": False,
        "insight_id": None,
    }

    # Log against notebook's first supporting KO or a synthetic subject
    subject = None
    if supporting_ko_ids:
        subject = (
            db.query(KnowledgeObject)
            .filter(KnowledgeObject.id == supporting_ko_ids[0])
            .first()
        )
    if subject:
        life_svc.record_event(
            db,
            subject,
            from_stage=subject.lifecycle_stage or "",
            to_stage=subject.lifecycle_stage or "",
            trigger="ai_recommend" if actor == "ai" else "score_reeval",
            actor=actor,
            payload={"insight_draft": draft, "accept": accept},
        )

    if accept:
        ko, insight = thinking_svc.create_insight(
            db,
            notebook_id=notebook_id,
            statement=statement,
            evidence_md=evidence_md,
            confidence=confidence,
            supporting_ko_ids=supporting_ko_ids,
            answers_question_id=question_id,
        )
        # Optional Insights folder sync when configured
        life_cfg = cfg()
        if life_cfg.get("insight_vault_folder") and life_cfg.get("sync_insights_to_vault"):
            from ..config import get_settings
            from . import workspace as workspace_svc

            settings = get_settings()
            vault = settings.default_vault_path
            if vault:
                ko.workspace_role = "insight"
                ko.graph_eligible = 0  # optional later
                db.commit()
                # Prefer reflection-linked sync if insight role not in workspace roles
                from . import knowledge as knowledge_svc

                if "insight" in knowledge_svc.WORKSPACE_NOTE_ROLES:
                    workspace_svc.sync_note(db, ko, vault_path=vault)
                else:
                    ko.workspace_role = "reflection"
                    ko.graph_eligible = 1
                    db.commit()
                    workspace_svc.sync_note(db, ko, vault_path=vault)
        draft["accepted"] = True
        draft["insight_id"] = insight.id

    return draft


def suggest_reading_for_question(
    db: Session, question_id: str, *, limit: int = 8
) -> dict[str, Any]:
    """Question gap-find: suggest Resource / KO ids by keyword overlap."""
    q = db.query(Question).filter(Question.id == question_id).first()
    qko = db.query(KnowledgeObject).filter(KnowledgeObject.id == question_id).first()
    if not q or not qko:
        raise ValueError("Question not found")
    tokens = {
        t
        for t in re.findall(r"[a-zA-Z\u4e00-\u9fff]{3,}", (q.statement or "").lower())
    }
    candidates = (
        db.query(KnowledgeObject)
        .filter(
            KnowledgeObject.notebook_id == qko.notebook_id,
            KnowledgeObject.lifecycle_stage.in_(("resource", "knowledge_object")),
        )
        .all()
    )
    scored: list[tuple[float, KnowledgeObject]] = []
    for cand in candidates:
        blob = f"{cand.title} {cand.summary} {' '.join(loads(cand.entities_json, []) or [])}".lower()
        hits = sum(1 for t in tokens if t in blob)
        if hits:
            scored.append((float(hits), cand))
    scored.sort(key=lambda x: x[0], reverse=True)
    suggestions = [
        {
            "ko_id": c.id,
            "title": c.title,
            "stage": c.lifecycle_stage,
            "score": s,
        }
        for s, c in scored[:limit]
    ]
    life_svc.record_event(
        db,
        qko,
        from_stage="question",
        to_stage="question",
        trigger="ai_recommend",
        actor="system",
        payload={"reading_suggestions": suggestions},
    )
    return {"question_id": question_id, "suggestions": suggestions}
