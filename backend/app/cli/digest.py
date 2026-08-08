"""CLI: generate daily/weekly digest and optionally email to DIGEST_TO.

Usage:
  python -m app.cli.digest --period daily --dry-run
  python -m app.cli.digest --period weekly
  python -m app.cli.digest --period daily --no-send
"""

from __future__ import annotations

import argparse
import json

from ..db import SessionLocal, init_db
from ..services.digest import run_digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate subscription digest")
    parser.add_argument("--period", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--notebook", default="", help="Notebook id (default: inbound)")
    parser.add_argument("--dry-run", action="store_true", help="Generate but do not persist/send")
    parser.add_argument("--no-send", action="store_true", help="Persist draft without SMTP")
    args = parser.parse_args(argv)

    init_db()
    db = SessionLocal()
    try:
        result = run_digest(
            db,
            period=args.period,
            notebook_id=args.notebook or None,
            send=not args.no_send and not args.dry_run,
            dry_run=args.dry_run,
        )
    finally:
        db.close()

    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if result.status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
