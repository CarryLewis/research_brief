"""CLI: Knowledge Graph Engine (cognitive projection — no visualization).

Usage:
  python -m app.cli.graph sync [--notebook nb_xxx]
  python -m app.cli.graph view --view research [--notebook nb_xxx] [--fresh]
  python -m app.cli.graph neighborhood --ko ko_xxx [--depth 2]
  python -m app.cli.graph path --from ko_a --to ko_b
  python -m app.cli.graph metrics [--notebook nb_xxx]
  python -m app.cli.graph stats [--notebook nb_xxx]
  python -m app.cli.graph timeline [--notebook nb_xxx]
  python -m app.cli.graph history --ko ko_xxx
  python -m app.cli.graph suggest-links --notebook nb_xxx
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from ..db import SessionLocal, init_db
from ..services import graph_engine as graph_svc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Knowledge Graph Engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sync = sub.add_parser("sync", help="Rebuild graph projection")
    p_sync.add_argument("--notebook", default="")

    p_view = sub.add_parser("view", help="Named cognitive view")
    p_view.add_argument("--view", default="default")
    p_view.add_argument("--notebook", default="")
    p_view.add_argument("--fresh", action="store_true")

    p_nb = sub.add_parser("neighborhood", help="Ego network")
    p_nb.add_argument("--ko", required=True)
    p_nb.add_argument("--depth", type=int, default=1)
    p_nb.add_argument("--notebook", default="")

    p_path = sub.add_parser("path", help="Shortest path")
    p_path.add_argument("--from", dest="from_id", required=True)
    p_path.add_argument("--to", dest="to_id", required=True)
    p_path.add_argument("--notebook", default="")

    p_met = sub.add_parser("metrics", help="Governance metrics")
    p_met.add_argument("--notebook", default="")
    p_met.add_argument("--series", action="store_true")

    p_st = sub.add_parser("stats", help="Counts by type/layer")
    p_st.add_argument("--notebook", default="")

    p_tl = sub.add_parser("timeline", help="Evolution frames")
    p_tl.add_argument("--notebook", default="")
    p_tl.add_argument("--since", default="")

    p_hist = sub.add_parser("history", help="Concept history")
    p_hist.add_argument("--ko", required=True)

    p_or = sub.add_parser("orphans", help="Orphan nodes")
    p_or.add_argument("--notebook", default="")

    p_sug = sub.add_parser("suggest-links", help="AI graph maintenance proposals")
    p_sug.add_argument("--notebook", required=True)

    args = parser.parse_args(argv)
    init_db()
    db = SessionLocal()
    try:
        nb = args.notebook or None if hasattr(args, "notebook") else None

        if args.cmd == "sync":
            print(json.dumps(graph_svc.sync_graph(db, nb), indent=2))
            return 0

        if args.cmd == "view":
            print(
                json.dumps(
                    graph_svc.get_view(
                        db, args.view, notebook_id=nb, fresh=args.fresh
                    ),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
            return 0

        if args.cmd == "neighborhood":
            print(
                json.dumps(
                    graph_svc.neighborhood(
                        db, args.ko, depth=args.depth, notebook_id=nb
                    ),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
            return 0

        if args.cmd == "path":
            print(
                json.dumps(
                    graph_svc.shortest_path(
                        db, args.from_id, args.to_id, notebook_id=nb
                    ),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
            return 0

        if args.cmd == "metrics":
            print(
                json.dumps(
                    graph_svc.get_metrics(db, notebook_id=nb, series=args.series),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
            return 0

        if args.cmd == "stats":
            print(json.dumps(graph_svc.graph_stats(db, notebook_id=nb), indent=2))
            return 0

        if args.cmd == "timeline":
            since = None
            if args.since:
                since = datetime.fromisoformat(args.since)
            print(
                json.dumps(
                    graph_svc.timeline(db, since=since, notebook_id=nb),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
            return 0

        if args.cmd == "history":
            print(
                json.dumps(
                    graph_svc.concept_history(db, args.ko),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
            return 0

        if args.cmd == "orphans":
            print(
                json.dumps(
                    {"orphans": graph_svc.list_orphans(db, notebook_id=nb)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.cmd == "suggest-links":
            print(
                json.dumps(
                    graph_svc.suggest_graph_links(db, notebook_id=args.notebook),
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
