"""CLI: process a normalized inbound email JSON (no webhook).

Usage:
  cd backend && source .venv/bin/activate
  python -m app.cli.inbound_email --file ../jobs/email_inbound_example.json
  python -m app.cli.inbound_email --file sample.json --no-analysis --no-media
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..config import PROJECT_ROOT, get_settings
from ..db import SessionLocal, init_db
from ..schemas import InboundEmailIn
from ..services.email_pipeline import process_inbound_email


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process inbound newsletter email JSON")
    parser.add_argument("--file", required=True, help="Path to InboundEmailIn JSON")
    parser.add_argument("--vault", type=str, default="", help="Obsidian vault path")
    parser.add_argument("--no-analysis", action="store_true", help="Skip LLM analysis")
    parser.add_argument("--no-chunks", action="store_true", help="Skip chunk indexing")
    parser.add_argument("--no-media", action="store_true", help="Skip media download")
    args = parser.parse_args(argv)

    init_db()
    settings = get_settings()

    path = Path(args.file).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    payload = InboundEmailIn.model_validate(data)

    vault = args.vault or settings.default_vault_path or str(PROJECT_ROOT / "vault")
    db = SessionLocal()
    try:
        result = process_inbound_email(
            db,
            payload,
            vault_path=vault,
            download_media=not args.no_media,
            run_analysis=not args.no_analysis,
            index_chunks=not args.no_chunks,
        )
    finally:
        db.close()

    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
