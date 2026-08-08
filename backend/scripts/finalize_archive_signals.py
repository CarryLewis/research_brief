#!/usr/bin/env python3
"""Finalize archive migration: historical signals are already kept → resource/KO."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.db import KnowledgeObject, SessionLocal, SourceDoc, init_db  # noqa: E402
from app.services import content_lake as lake  # noqa: E402
from app.services import graph_engine as graph_svc  # noqa: E402
from app.services import lifecycle as life_svc  # noqa: E402
from app.utils import loads  # noqa: E402

ARCHIVE_NBS = {
    "nb_archive_kazke",
    "nb_archive_pubmed",
    "nb_archive_misc",
    "nb_a519e4963d75",
}


def main() -> int:
    init_db()
    db = SessionLocal()
    fixed = 0
    try:
        for ko in db.query(KnowledgeObject).filter(
            KnowledgeObject.notebook_id.in_(ARCHIVE_NBS)
        ).all():
            if (ko.lifecycle_stage or "") != "signal":
                continue
            src = None
            if ko.source_doc_id:
                src = db.query(SourceDoc).filter(SourceDoc.id == ko.source_doc_id).first()
            if src and (src.raw_text or "").strip() and not ko.primary_content_uri:
                ref = lake.put_text(
                    db,
                    src.raw_text,
                    mime="text/plain",
                    role="original",
                    ko_id=ko.id,
                    filename=f"{ko.id}.txt",
                )
                ko.primary_content_uri = ref.uri
                db.commit()
            life_svc.keep_signal(db, ko, actor="system")
            db.refresh(ko)
            if (ko.summary or "").strip() or loads(ko.entities_json, []):
                life_svc.mark_analyzed(db, ko, confidence=float(ko.confidence or 0.45))
            elif (ko.lifecycle_stage or "") != "knowledge_object":
                # keep_signal already advanced to resource
                pass
            ko.filter_status = "kept"
            ko.workspace_role = "resource"
            ko.graph_eligible = 0
            ko.vault_path = None
            db.commit()
            fixed += 1

        drive = (
            db.query(KnowledgeObject)
            .filter(KnowledgeObject.title == "Driving risk")
            .first()
        )
        if drive:
            drive.workspace_role = "resource"
            drive.graph_eligible = 0
            db.commit()

        for nb in ARCHIVE_NBS:
            graph_svc.sync_graph(db, nb)

        stages = Counter(
            k.lifecycle_stage
            for k in db.query(KnowledgeObject)
            .filter(KnowledgeObject.notebook_id.in_(ARCHIVE_NBS))
            .all()
        )
        print({"fixed_signals": fixed, "stages": dict(stages)})
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
