"""CLI: Thinking Vault Notion → Obsidian sync.

Usage:
  python -m app.cli.thinking_sync
  python -m app.cli.thinking_sync --vault /path/to/vault
  python -m app.cli.thinking_sync --status
  python -m app.cli.thinking_sync --no-archive-missing
"""

from __future__ import annotations

import argparse
import json
import sys

from ..config import get_settings
from ..db import SessionLocal, init_db
from ..services import thinking_vault as thinking_vault_svc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync Notion Thinking Database → Obsidian Thinking/"
    )
    parser.add_argument("--vault", default="", help="Obsidian vault path")
    parser.add_argument(
        "--no-archive-missing",
        action="store_true",
        help="Do not soft-archive Obsidian notes missing from Notion",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print sync index status and exit",
    )
    args = parser.parse_args(argv)

    init_db()
    settings = get_settings()
    db = SessionLocal()
    try:
        if args.status:
            print(json.dumps(thinking_vault_svc.last_sync_status(db), ensure_ascii=False, indent=2))
            return 0

        vault = (args.vault or settings.default_vault_path or "").strip()
        if not vault:
            print("vault path required (--vault or DEFAULT_VAULT_PATH)", file=sys.stderr)
            return 2
        token = (settings.notion_token or "").strip()
        database_id = (settings.notion_thinking_database_id or "").strip()
        if not token:
            print("NOTION_TOKEN is not configured", file=sys.stderr)
            return 2
        if not database_id:
            print("NOTION_THINKING_DATABASE_ID is not configured", file=sys.stderr)
            return 2

        result = thinking_vault_svc.sync_from_notion(
            db,
            vault_path=vault,
            token=token,
            database_id=database_id,
            soft_archive_missing=not args.no_archive_missing,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 1 if result.errors else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
