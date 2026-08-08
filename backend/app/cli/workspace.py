"""CLI: Research Workspace curation (Constitution V1).

Usage:
  python -m app.cli.workspace suggestions
  python -m app.cli.workspace promote --id ko_xxx --role concept
  python -m app.cli.workspace demote --id ko_xxx
  python -m app.cli.workspace accept --suggestion sug_xxx --notebook nb_xxx
  python -m app.cli.workspace sync --notebook nb_xxx
"""

from __future__ import annotations

import argparse
import json

from ..config import get_settings
from ..db import ConceptSuggestion, SessionLocal, init_db
from ..services import knowledge as knowledge_svc
from ..services import workspace as workspace_svc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Curate Research Workspace notes")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sug = sub.add_parser("suggestions", help="List concept suggestions")
    p_sug.add_argument("--notebook", default="")

    p_promo = sub.add_parser("promote", help="Promote a Resource KO to a workspace note")
    p_promo.add_argument("--id", required=True, help="Knowledge object id")
    p_promo.add_argument(
        "--role",
        required=True,
        choices=["concept", "project", "reflection", "book"],
    )
    p_promo.add_argument("--title", default="")
    p_promo.add_argument("--vault", default="")
    p_promo.add_argument("--no-sync", action="store_true")

    p_dem = sub.add_parser("demote", help="Archive a workspace note (keep DB/Lake)")
    p_dem.add_argument("--id", required=True)
    p_dem.add_argument("--vault", default="")

    p_acc = sub.add_parser("accept", help="Accept a concept suggestion")
    p_acc.add_argument("--suggestion", required=True)
    p_acc.add_argument("--notebook", default="")
    p_acc.add_argument("--vault", default="")

    p_sync = sub.add_parser("sync", help="Sync all promoted notes for a notebook")
    p_sync.add_argument("--notebook", default="")
    p_sync.add_argument("--vault", default="")

    args = parser.parse_args(argv)
    init_db()
    settings = get_settings()
    db = SessionLocal()
    try:
        if args.cmd == "suggestions":
            rows = knowledge_svc.list_concept_suggestions(
                db, notebook_id=args.notebook or None
            )
            out = [
                {
                    "id": r.id,
                    "entity_name": r.entity_name,
                    "mention_count": r.mention_count,
                    "status": r.status,
                    "message": r.message,
                    "notebook_id": r.notebook_id,
                }
                for r in rows
            ]
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0

        if args.cmd == "promote":
            ko = knowledge_svc.get_by_id(db, args.id)
            if not ko:
                print(json.dumps({"error": "not found"}))
                return 1
            vault = args.vault or settings.default_vault_path or None
            ko = knowledge_svc.promote(
                db,
                ko,
                args.role,
                title=args.title or None,
                vault_path=vault,
                sync=not args.no_sync,
            )
            print(
                json.dumps(
                    {
                        "id": ko.id,
                        "title": ko.title,
                        "workspace_role": ko.workspace_role,
                        "vault_path": ko.vault_path,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "demote":
            ko = knowledge_svc.get_by_id(db, args.id)
            if not ko:
                print(json.dumps({"error": "not found"}))
                return 1
            vault = args.vault or settings.default_vault_path or None
            ko = knowledge_svc.demote(db, ko, vault_path=vault)
            print(
                json.dumps(
                    {
                        "id": ko.id,
                        "workspace_role": ko.workspace_role,
                        "vault_path": ko.vault_path,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "accept":
            sug = (
                db.query(ConceptSuggestion)
                .filter(ConceptSuggestion.id == args.suggestion)
                .first()
            )
            if not sug:
                print(json.dumps({"error": "suggestion not found"}))
                return 1
            vault = args.vault or settings.default_vault_path or None
            ko = knowledge_svc.create_concept_from_suggestion(
                db,
                sug,
                vault_path=vault,
                notebook_id=args.notebook or sug.notebook_id,
            )
            print(
                json.dumps(
                    {
                        "id": ko.id,
                        "title": ko.title,
                        "workspace_role": ko.workspace_role,
                        "vault_path": ko.vault_path,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "sync":
            vault = args.vault or settings.default_vault_path
            if not vault:
                print(json.dumps({"error": "vault_path required"}))
                return 1
            result = workspace_svc.sync_workspace_notes(
                db, vault_path=vault, notebook_id=args.notebook or None
            )
            print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
            return 0

        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
