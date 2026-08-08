"""CLI: Knowledge Lifecycle Engine.

Usage:
  python -m app.cli.lifecycle backfill
  python -m app.cli.lifecycle evaluate --notebook nb_xxx
  python -m app.cli.lifecycle proposals
  python -m app.cli.lifecycle accept --proposal lpr_xxx
  python -m app.cli.lifecycle evolution --ko ko_xxx
  python -m app.cli.lifecycle central
  python -m app.cli.lifecycle questions --status open
  python -m app.cli.lifecycle filter-signal --ko ko_xxx [--apply]
  python -m app.cli.lifecycle assist-reflection --id ko_xxx
  python -m app.cli.lifecycle project-context --id ko_xxx
  python -m app.cli.lifecycle draft-insight --notebook nb_xxx --support ko_a,ko_b
"""

from __future__ import annotations

import argparse
import json

from ..config import get_settings
from ..db import KnowledgeObject, LifecycleProposal, SessionLocal, init_db
from ..services import lifecycle as life_svc
from ..services import lifecycle_ai as life_ai
from ..services import thinking as thinking_svc
from ..utils import loads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Knowledge Lifecycle Engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("backfill", help="Backfill lifecycle_stage from existing KOs")

    p_eval = sub.add_parser("evaluate", help="Recompute scores and emit proposals")
    p_eval.add_argument("--notebook", default="")

    p_prop = sub.add_parser("proposals", help="List pending proposals")
    p_prop.add_argument("--notebook", default="")

    p_acc = sub.add_parser("accept", help="Accept a lifecycle proposal")
    p_acc.add_argument("--proposal", required=True)
    p_acc.add_argument("--vault", default="")
    p_acc.add_argument("--no-sync", action="store_true")

    p_dis = sub.add_parser("dismiss", help="Dismiss a proposal")
    p_dis.add_argument("--proposal", required=True)

    p_evo = sub.add_parser("evolution", help="Show evolution timeline for a KO")
    p_evo.add_argument("--ko", required=True)

    p_cen = sub.add_parser("central", help="List central concepts by score")
    p_cen.add_argument("--notebook", default="")
    p_cen.add_argument("--limit", type=int, default=20)

    p_q = sub.add_parser("questions", help="List research questions")
    p_q.add_argument("--notebook", default="")
    p_q.add_argument("--status", default="open")

    p_ins = sub.add_parser("insights", help="List insights")
    p_ins.add_argument("--notebook", default="")

    p_fs = sub.add_parser("filter-signal", help="Filter a signal (keep/discard)")
    p_fs.add_argument("--ko", required=True)
    p_fs.add_argument("--apply", action="store_true")
    p_fs.add_argument("--no-llm", action="store_true")

    p_ar = sub.add_parser("assist-reflection", help="Suggest questions from a reflection")
    p_ar.add_argument("--id", required=True)
    p_ar.add_argument("--create", action="store_true")
    p_ar.add_argument("--no-llm", action="store_true")

    p_pc = sub.add_parser("project-context", help="Project knowledge hub context pack")
    p_pc.add_argument("--id", required=True)

    p_di = sub.add_parser("draft-insight", help="Draft an insight (accept with --accept)")
    p_di.add_argument("--notebook", required=True)
    p_di.add_argument("--support", default="", help="Comma-separated KO ids")
    p_di.add_argument("--question", default="")
    p_di.add_argument("--accept", action="store_true")
    p_di.add_argument("--no-llm", action="store_true")

    p_rd = sub.add_parser("reading", help="Suggest reading for a question")
    p_rd.add_argument("--question", required=True)

    args = parser.parse_args(argv)
    init_db()
    settings = get_settings()
    db = SessionLocal()
    try:
        if args.cmd == "backfill":
            print(json.dumps(life_svc.backfill_lifecycle(db), indent=2))
            return 0

        if args.cmd == "evaluate":
            props = life_svc.evaluate_workspace(db, args.notebook or None)
            print(
                json.dumps(
                    {
                        "count": len(props),
                        "proposals": [
                            {
                                "id": p.id,
                                "ko_id": p.ko_id,
                                "maturity": p.proposed_maturity,
                                "score": p.score,
                                "reason": p.reason,
                            }
                            for p in props
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "proposals":
            rows = life_svc.list_proposals(db, notebook_id=args.notebook or None)
            print(
                json.dumps(
                    [
                        {
                            "id": r.id,
                            "ko_id": r.ko_id,
                            "proposed_maturity": r.proposed_maturity,
                            "score": r.score,
                            "reason": r.reason,
                            "status": r.status,
                        }
                        for r in rows
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "accept":
            prop = (
                db.query(LifecycleProposal)
                .filter(LifecycleProposal.id == args.proposal)
                .first()
            )
            if not prop:
                print(json.dumps({"error": "not found"}))
                return 1
            vault = args.vault or settings.default_vault_path or None
            ko = life_svc.accept_proposal(
                db, prop, sync_workspace=not args.no_sync, vault_path=vault
            )
            print(
                json.dumps(
                    {
                        "id": ko.id,
                        "title": ko.title,
                        "lifecycle_stage": ko.lifecycle_stage,
                        "maturity": ko.maturity,
                        "vault_path": ko.vault_path,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "dismiss":
            prop = (
                db.query(LifecycleProposal)
                .filter(LifecycleProposal.id == args.proposal)
                .first()
            )
            if not prop:
                print(json.dumps({"error": "not found"}))
                return 1
            prop = life_svc.dismiss_proposal(db, prop)
            print(json.dumps({"id": prop.id, "status": prop.status}))
            return 0

        if args.cmd == "evolution":
            events = life_svc.list_evolution(db, args.ko)
            print(
                json.dumps(
                    [
                        {
                            "id": e.id,
                            "from": e.from_stage,
                            "to": e.to_stage,
                            "maturity": f"{e.from_maturity}->{e.to_maturity}",
                            "trigger": e.trigger,
                            "actor": e.actor,
                            "at": e.created_at.isoformat() if e.created_at else None,
                            "payload": loads(e.payload_json, {}),
                        }
                        for e in events
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "central":
            rows = life_svc.list_central_concepts(
                db, notebook_id=args.notebook or None, limit=args.limit
            )
            print(
                json.dumps(
                    [
                        {
                            "id": ko.id,
                            "title": ko.title,
                            "maturity": prof.maturity_level,
                            "score": prof.promotion_score,
                            "mentions": prof.mention_count,
                            "reflections": prof.reflection_count,
                        }
                        for ko, prof in rows
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "questions":
            rows = thinking_svc.list_questions(
                db, notebook_id=args.notebook or None, status=args.status or None
            )
            print(
                json.dumps(
                    [
                        {
                            "id": ko.id,
                            "title": ko.title,
                            "statement": q.statement,
                            "status": q.status,
                            "priority": q.priority,
                        }
                        for ko, q in rows
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "insights":
            rows = thinking_svc.list_insights(db, notebook_id=args.notebook or None)
            print(
                json.dumps(
                    [
                        {
                            "id": ko.id,
                            "title": ko.title,
                            "statement": ins.statement,
                            "confidence": ins.confidence,
                            "status": ins.status,
                        }
                        for ko, ins in rows
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "filter-signal":
            ko = db.query(KnowledgeObject).filter(KnowledgeObject.id == args.ko).first()
            if not ko:
                print(json.dumps({"error": "not found"}))
                return 1
            print(
                json.dumps(
                    life_ai.filter_signal(
                        db, ko, apply=args.apply, use_llm=not args.no_llm
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "assist-reflection":
            print(
                json.dumps(
                    life_ai.suggest_questions_from_reflection(
                        db,
                        args.id,
                        create=args.create,
                        use_llm=not args.no_llm,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "project-context":
            print(
                json.dumps(
                    life_ai.project_context_pack(db, args.id),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "draft-insight":
            supports = [x.strip() for x in (args.support or "").split(",") if x.strip()]
            print(
                json.dumps(
                    life_ai.draft_insight(
                        db,
                        notebook_id=args.notebook,
                        supporting_ko_ids=supports,
                        question_id=args.question or None,
                        use_llm=not args.no_llm,
                        accept=args.accept,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "reading":
            print(
                json.dumps(
                    life_ai.suggest_reading_for_question(db, args.question),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
