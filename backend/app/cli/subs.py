"""CLI: manage subscription catalog.

Usage:
  python -m app.cli.subs list
  python -m app.cli.subs add --name "Lenny" --pattern "*@lenny.com" --tag product
  python -m app.cli.subs disable --id sub_xxx
  python -m app.cli.subs enable --id sub_xxx
  python -m app.cli.subs delete --id sub_xxx
"""

from __future__ import annotations

import argparse
import json

from ..db import SessionLocal, init_db
from ..schemas import SubscriptionCreate, SubscriptionUpdate
from ..services import subscriptions as subs_svc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage newsletter subscription catalog")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List subscriptions")
    p_list.add_argument("--enabled-only", action="store_true")

    p_add = sub.add_parser("add", help="Add subscription")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--pattern", required=True, help="e.g. *@substack.com or news@x.com")
    p_add.add_argument("--tag", action="append", default=[], help="Tag (repeatable)")
    p_add.add_argument("--notes", default="")
    p_add.add_argument("--disabled", action="store_true")

    p_dis = sub.add_parser("disable", help="Disable subscription")
    p_dis.add_argument("--id", required=True)

    p_en = sub.add_parser("enable", help="Enable subscription")
    p_en.add_argument("--id", required=True)

    p_del = sub.add_parser("delete", help="Delete subscription")
    p_del.add_argument("--id", required=True)

    args = parser.parse_args(argv)
    init_db()
    db = SessionLocal()
    try:
        if args.cmd == "list":
            rows = subs_svc.list_subscriptions(db, enabled_only=args.enabled_only)
            print(json.dumps([r.model_dump(mode="json") for r in rows], ensure_ascii=False, indent=2))
        elif args.cmd == "add":
            out = subs_svc.create_subscription(
                db,
                SubscriptionCreate(
                    name=args.name,
                    sender_pattern=args.pattern,
                    enabled=not args.disabled,
                    tags=args.tag,
                    notes=args.notes,
                ),
            )
            print(json.dumps(out.model_dump(mode="json"), ensure_ascii=False, indent=2))
        elif args.cmd == "disable":
            row = subs_svc.get_subscription(db, args.id)
            if not row:
                print(json.dumps({"error": "not found"}))
                return 1
            out = subs_svc.update_subscription(db, row, SubscriptionUpdate(enabled=False))
            print(json.dumps(out.model_dump(mode="json"), ensure_ascii=False, indent=2))
        elif args.cmd == "enable":
            row = subs_svc.get_subscription(db, args.id)
            if not row:
                print(json.dumps({"error": "not found"}))
                return 1
            out = subs_svc.update_subscription(db, row, SubscriptionUpdate(enabled=True))
            print(json.dumps(out.model_dump(mode="json"), ensure_ascii=False, indent=2))
        elif args.cmd == "delete":
            row = subs_svc.get_subscription(db, args.id)
            if not row:
                print(json.dumps({"error": "not found"}))
                return 1
            subs_svc.delete_subscription(db, row)
            print(json.dumps({"ok": True, "id": args.id}))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
