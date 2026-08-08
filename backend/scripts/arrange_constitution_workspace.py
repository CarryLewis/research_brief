#!/usr/bin/env python3
"""One-shot: arrange existing sources into Constitution + Lifecycle + Graph.

- Scaffold Constitution folders on target vault(s)
- Archive legacy Inbox / 01_Raw / 20_Sources
- Structure migraine Resources from Lake text (no LLM required)
- Create Project / Concepts / Reflection / Questions
- Clear stale Knowledge/Inbox vault_paths on Resources
- Lifecycle backfill + Graph sync + workspace note sync
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.config import get_settings  # noqa: E402
from app.db import (  # noqa: E402
    KnowledgeObject,
    KoLink,
    Notebook,
    SessionLocal,
    init_db,
    utcnow,
)
from app.schemas import AnalysisOut  # noqa: E402
from app.services import content_lake as lake_svc  # noqa: E402
from app.services import graph_engine as graph_svc  # noqa: E402
from app.services import knowledge as knowledge_svc  # noqa: E402
from app.services import lifecycle as life_svc  # noqa: E402
from app.services import thinking as thinking_svc  # noqa: E402
from app.services import workspace as workspace_svc  # noqa: E402
from app.utils import dumps, loads, new_id  # noqa: E402

MIGRAINE_NOTEBOOK_ID = "nb_a519e4963d75"
MIGRAINE_NOTEBOOK_TITLE = "Nature migraine research"

# Titles / keywords that belong in the Migraine project hub
MIGRAINE_HINTS = re.compile(
    r"migraine|nitroglycerin|multisensory|connectivity mapping|light logger|driving",
    re.I,
)


def scaffold_and_archive(vault: Path) -> dict:
    vault.mkdir(parents=True, exist_ok=True)
    workspace_svc.ensure_scaffold(vault)
    (vault / "Insights").mkdir(parents=True, exist_ok=True)

    archive = vault / "Archive"
    legacy = archive / "Legacy"
    legacy.mkdir(parents=True, exist_ok=True)
    moved = []

    for name in ("00_Inbox", "20_Sources", "01_Raw"):
        src = vault / name
        if not src.exists():
            continue
        dest = legacy / name
        if dest.exists():
            # merge: move children then remove
            for child in src.iterdir():
                target = dest / child.name
                if target.exists():
                    continue
                shutil.move(str(child), str(target))
            shutil.rmtree(src, ignore_errors=True)
        else:
            shutil.move(str(src), str(dest))
        moved.append(name)

    # Knowledge/ leftover if any
    knowledge = vault / "Knowledge"
    if knowledge.exists():
        dest = archive / "PreConstitution-Knowledge"
        if not dest.exists():
            shutil.move(str(knowledge), str(dest))
            moved.append("Knowledge")
        else:
            for child in knowledge.iterdir():
                t = dest / child.name
                if not t.exists():
                    shutil.move(str(child), str(t))
            shutil.rmtree(knowledge, ignore_errors=True)
            moved.append("Knowledge")

    welcome = vault / "Welcome.md"
    welcome.write_text(
        """---
title: Welcome
type: meta
tags:
  - meta
updated: 2026-08-02
---

# Research Workspace (Constitution V1)

This vault is a **thinking laboratory**, not an archive.

## Layers

1. **Content Lake** — originals (outside Obsidian)
2. **Knowledge Database** — Resources, lifecycle, graph projection (SQLite)
3. **Research Workspace** — this vault (curated notes only)
4. **Graph Engine** — cognitive JSON API (not Obsidian Graph)

## Folders

- `Projects/` — research hubs
- `Concepts/` — long-term ideas
- `Reflections/` — personal understanding
- `Books/` — one book, one note
- `Insights/` — optional high-level synthesis notes
- `Reports/` — digests (`graph: false`)
- `Collections/` — human indexes only
- `Archive/Legacy/` — old Inbox / 01_Raw / Sources
- `Archive/PreConstitution-Inbox/` — former auto paper dumps

## Rule

Articles and papers stay in the Knowledge Database as Resources.
Promote deliberately into Concept / Project / Reflection / Book.
""",
        encoding="utf-8",
    )
    return {"vault": str(vault), "archived": moved}


def _lake_text(ko: KnowledgeObject) -> str:
    if ko.primary_content_uri:
        try:
            return lake_svc.read_text(ko.primary_content_uri) or ""
        except Exception:  # noqa: BLE001
            pass
    return ""


def _heuristic_analysis(title: str, text: str) -> AnalysisOut:
    blob = f"{title}\n{text}"
    # Simple entity harvest from title + capitalized / domain terms
    entities = []
    for term in (
        "Migraine",
        "Stroke",
        "Inflammation",
        "CGRP",
        "Multisensory integration",
        "Functional connectivity",
        "Mismatch negativity",
        "Psychological intervention",
        "Driving risk",
        "Light logger",
        "Nitroglycerin",
        "Episodic migraine",
    ):
        if re.search(re.escape(term), blob, re.I):
            entities.append(term)
    if "migraine" in blob.lower() and "Migraine" not in entities:
        entities.insert(0, "Migraine")

    # Key points: first 3 non-empty sentences from abstract-ish text
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    key_points = [s.strip() for s in sentences if len(s.strip()) > 40][:5]
    if not key_points and text.strip():
        key_points = [text.strip()[:240]]

    summary = (text.strip()[:500] if text.strip() else title).replace("\n", " ")
    tags = ["medicine", "neurology", "research"]
    if "migraine" in blob.lower():
        tags.append("stroke")  # allowlist has stroke; keep medicine focus
        tags = ["medicine", "neurology", "research", "clinical"]

    return AnalysisOut(
        summary=summary,
        tags=tags[:5],
        key_points=key_points,
        entities=entities[:12],
        followup_urls=[],
    )


def _ensure_edge(
    db,
    *,
    from_ko_id: str,
    to_ko_id: str,
    edge_type: str,
    from_type: str = "ko",
    to_type: str = "ko",
    created_by: str = "user",
    evidence: str = "",
) -> None:
    exists = (
        db.query(KoLink)
        .filter(
            KoLink.from_ko_id == from_ko_id,
            KoLink.to_ko_id == to_ko_id,
            KoLink.link_type == edge_type,
        )
        .first()
    )
    if exists:
        return
    life_svc.create_edge(
        db,
        from_ko_id=from_ko_id,
        to_ko_id=to_ko_id,
        edge_type=edge_type,
        from_type=from_type,
        to_type=to_type,
        created_by=created_by,
        evidence=evidence,
    )


def ensure_migraine_notebook(db) -> Notebook:
    nb = db.query(Notebook).filter(Notebook.id == MIGRAINE_NOTEBOOK_ID).first()
    if nb:
        nb.title = MIGRAINE_NOTEBOOK_TITLE
        db.commit()
        return nb
    nb = Notebook(
        id=MIGRAINE_NOTEBOOK_ID,
        title=MIGRAINE_NOTEBOOK_TITLE,
        topic="migraine",
    )
    db.add(nb)
    db.commit()
    return nb


def structure_resources(db) -> list[KnowledgeObject]:
    """Move migraine-related papers to hub notebook; analyze from Lake; clear vault_path."""
    ensure_migraine_notebook(db)
    selected: list[KnowledgeObject] = []
    for ko in db.query(KnowledgeObject).filter(KnowledgeObject.kind == "paper").all():
        title = ko.title or ""
        if not MIGRAINE_HINTS.search(title):
            # Still clear stale Inbox paths
            if ko.vault_path and (
                "Knowledge/Inbox" in ko.vault_path or "Inbox/" in ko.vault_path
            ):
                ko.vault_path = None
                ko.workspace_role = "resource"
                ko.graph_eligible = 0
            continue

        ko.notebook_id = MIGRAINE_NOTEBOOK_ID
        ko.workspace_role = "resource"
        ko.graph_eligible = 0
        if ko.vault_path and (
            "Knowledge/Inbox" in ko.vault_path or ko.vault_path.startswith("Inbox")
        ):
            ko.vault_path = None

        text = _lake_text(ko)
        analysis = _heuristic_analysis(title, text)
        knowledge_svc.apply_analysis(db, ko, analysis)
        life_svc.mark_analyzed(db, ko, confidence=0.55)
        selected.append(ko)

    db.commit()
    # Dedupe by title: keep one per normalized title in notebook
    seen: set[str] = set()
    unique: list[KnowledgeObject] = []
    for ko in selected:
        key = re.sub(r"\s+", " ", (ko.title or "").lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(ko)
    return unique


def ensure_hub(db, vault: str, papers: list[KnowledgeObject]) -> dict:
    # Project
    project = (
        db.query(KnowledgeObject)
        .filter(
            KnowledgeObject.notebook_id == MIGRAINE_NOTEBOOK_ID,
            KnowledgeObject.workspace_role == "project",
            KnowledgeObject.title == "Nature Migraine Research",
        )
        .first()
    )
    if not project:
        project = KnowledgeObject(
            id=new_id("ko"),
            notebook_id=MIGRAINE_NOTEBOOK_ID,
            kind="project",
            title="Nature Migraine Research",
            summary=(
                "Hub for Nature-portfolio migraine papers: interventions, "
                "connectivity, sensory load, behavioral risk, and models."
            ),
            key_points_json=dumps(
                [
                    "Keep papers as Resources in the Knowledge Database",
                    "Promote Concepts only when evidence accumulates",
                    "Reflections and Questions drive the research agenda",
                ]
            ),
            status="ready",
            connector="manual",
            content_hash=new_id("h"),
            tags_json=dumps(["medicine", "neurology", "research"]),
            entities_json=dumps(["Migraine"]),
            metadata_json="{}",
            workspace_role="project",
            graph_eligible=1,
            lifecycle_stage="project",
            lifecycle_updated_at=utcnow(),
        )
        db.add(project)
        db.commit()
        life_svc.ensure_project_profile(db, project)
        life_svc.record_event(
            db,
            project,
            from_stage="",
            to_stage="project",
            trigger="user_promote",
            actor="user",
            payload={"arranged": True},
        )

    # Concepts
    concept_names = [
        ("Migraine", "core"),
        ("Psychological intervention", "emerging"),
        ("Functional connectivity", "emerging"),
        ("Multisensory integration", "emerging"),
        ("Mismatch negativity", "candidate"),
    ]
    concepts: dict[str, KnowledgeObject] = {}
    for name, maturity in concept_names:
        c = (
            db.query(KnowledgeObject)
            .filter(
                KnowledgeObject.notebook_id == MIGRAINE_NOTEBOOK_ID,
                KnowledgeObject.kind == "concept",
                KnowledgeObject.title == name,
            )
            .first()
        )
        if not c:
            c = KnowledgeObject(
                id=new_id("ko"),
                notebook_id=MIGRAINE_NOTEBOOK_ID,
                kind="concept",
                title=name,
                summary=f"Working concept hub for {name} within migraine research.",
                key_points_json="[]",
                status="ready",
                connector="manual",
                content_hash=new_id("h"),
                tags_json=dumps(["medicine", "neurology"]),
                entities_json=dumps([name]),
                metadata_json="{}",
                workspace_role="concept",
                graph_eligible=1,
                lifecycle_stage="concept",
                maturity=maturity,
                confidence=0.6,
                lifecycle_updated_at=utcnow(),
            )
            db.add(c)
            db.commit()
            life_svc.ensure_concept_profile(db, c)
            life_svc.record_event(
                db,
                c,
                from_stage="",
                to_stage="concept",
                to_maturity=maturity,
                trigger="user_promote",
                actor="user",
                payload={"arranged": True},
            )
        concepts[name] = c
        _ensure_edge(
            db,
            from_ko_id=c.id,
            to_ko_id=project.id,
            edge_type="member_of",
            from_type="concept",
            to_type="project",
        )

    # Link papers → Migraine concept + project
    migraine = concepts["Migraine"]
    for paper in papers:
        _ensure_edge(
            db,
            from_ko_id=paper.id,
            to_ko_id=migraine.id,
            edge_type="about",
            from_type="ko",
            to_type="concept",
            created_by="system",
            evidence="title/entity match",
        )
        _ensure_edge(
            db,
            from_ko_id=paper.id,
            to_ko_id=project.id,
            edge_type="member_of",
            from_type="ko",
            to_type="project",
            created_by="system",
        )
        ents = [e.lower() for e in (loads(paper.entities_json, []) or [])]
        for name, c in concepts.items():
            if name == "Migraine":
                continue
            if name.lower() in " ".join(ents) or name.lower() in (paper.title or "").lower():
                _ensure_edge(
                    db,
                    from_ko_id=paper.id,
                    to_ko_id=c.id,
                    edge_type="about",
                    from_type="ko",
                    to_type="concept",
                    created_by="system",
                )

    # Reflection
    ref_existing = (
        db.query(KnowledgeObject)
        .filter(
            KnowledgeObject.notebook_id == MIGRAINE_NOTEBOOK_ID,
            KnowledgeObject.title == "Migraine research — opening notes",
        )
        .first()
    )
    if not ref_existing:
        body = """## Opening arrangement (Constitution)

Papers stay as **Resources** in the Knowledge Database (Content Lake).
This vault only holds the Project hub, Concepts, and this Reflection.

### Working map
- [[Migraine]] is the backbone concept
- Psychological intervention, connectivity, and multisensory themes are emerging
- Mismatch negativity is a candidate from model work

### Open questions
- Which connectivity patterns best predict episodic migraine severity?
- How do psychological interventions interact with sensory load and fatigue?
- Can light-logger adherence become a reliable behavioral phenotype?

Resources remain queryable via search — they are not vault files.
"""
        related = [project.id, migraine.id] + [
            concepts[n].id
            for n in (
                "Psychological intervention",
                "Functional connectivity",
                "Multisensory integration",
            )
        ]
        rko, _ = thinking_svc.create_reflection(
            db,
            notebook_id=MIGRAINE_NOTEBOOK_ID,
            title="Migraine research — opening notes",
            body_md=body,
            author="arrangement",
            related_ko_ids=related,
            vault_path=vault,
            sync=True,
        )
        _ensure_edge(
            db,
            from_ko_id=rko.id,
            to_ko_id=project.id,
            edge_type="member_of",
            from_type="reflection",
            to_type="project",
        )
    else:
        rko = ref_existing

    # Questions
    for statement in (
        "Which connectivity patterns best predict episodic migraine severity?",
        "How do psychological interventions interact with sensory load?",
        "Can light-logger adherence become a reliable behavioral phenotype?",
    ):
        exists = (
            db.query(KnowledgeObject)
            .filter(
                KnowledgeObject.notebook_id == MIGRAINE_NOTEBOOK_ID,
                KnowledgeObject.kind == "question",
                KnowledgeObject.summary == statement,
            )
            .first()
        )
        if exists:
            continue
        qko, _ = thinking_svc.create_question(
            db,
            notebook_id=MIGRAINE_NOTEBOOK_ID,
            statement=statement,
            related_ko_ids=[migraine.id, project.id],
        )
        _ensure_edge(
            db,
            from_ko_id=qko.id,
            to_ko_id=project.id,
            edge_type="member_of",
            from_type="question",
            to_type="project",
        )

    # Sync project + concepts to vault (already have correct workspace_role)
    for ko in [project, *concepts.values()]:
        role = (ko.workspace_role or "").lower()
        if role not in {"concept", "project", "reflection", "book"}:
            continue
        db.refresh(ko)
        workspace_svc.sync_note(db, ko, vault_path=vault)

    life_svc.evaluate_workspace(db, MIGRAINE_NOTEBOOK_ID)
    life_svc.backfill_lifecycle(db)
    graph_stats = graph_svc.sync_graph(db, MIGRAINE_NOTEBOOK_ID)
    export = workspace_svc.sync_workspace_notes(
        db, vault_path=vault, notebook_id=MIGRAINE_NOTEBOOK_ID
    )

    return {
        "notebook_id": MIGRAINE_NOTEBOOK_ID,
        "papers": len(papers),
        "project_id": project.id,
        "concepts": list(concepts.keys()),
        "reflection_id": rko.id,
        "graph": graph_stats,
        "synced_notes": getattr(export, "sources_written", None),
    }


def main() -> int:
    init_db()
    settings = get_settings()
    repo_vault = REPO / "vault"
    live_vault = Path(settings.default_vault_path).expanduser() if settings.default_vault_path else None

    results = {"scaffolds": []}
    for vault in [repo_vault] + ([live_vault] if live_vault else []):
        if vault is None:
            continue
        results["scaffolds"].append(scaffold_and_archive(vault))

    db = SessionLocal()
    try:
        papers = structure_resources(db)
        # Prefer syncing curated notes to live vault if available, else repo vault
        target = str(live_vault) if live_vault and live_vault.exists() else str(repo_vault)
        # Also sync repo vault for the in-repo demo
        hub_live = ensure_hub(db, target, papers)
        if str(repo_vault) != target:
            # Mirror workspace notes into repo vault too
            workspace_svc.sync_workspace_notes(
                db, vault_path=str(repo_vault), notebook_id=MIGRAINE_NOTEBOOK_ID
            )
        results["hub"] = hub_live
        results["target_vault"] = target
        view = graph_svc.get_view(db, "research", notebook_id=MIGRAINE_NOTEBOOK_ID)
        results["research_view"] = {
            "nodes": len(view["nodes"]),
            "edges": len(view["edges"]),
            "types": sorted({n["node_type"] for n in view["nodes"]}),
        }
    finally:
        db.close()

    import json

    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
