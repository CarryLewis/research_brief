"""CLI: collect raw materials into Obsidian.

Usage:
  cd backend && source .venv/bin/activate
  python -m app.cli.collect --job ../jobs/example.yaml
  python -m app.cli.collect --topic "GLP-1" --url https://example.com --channel pubmed
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from ..config import PROJECT_ROOT, get_settings
from ..db import SessionLocal, init_db
from ..schemas import CollectRequest, ScopeSpec
from ..services.collect import run_collect


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch raw text/media into Obsidian vault")
    parser.add_argument("--job", type=str, help="YAML job file")
    parser.add_argument("--topic", type=str, help="What you want to learn about")
    parser.add_argument("--title", type=str, default="", help="Job title")
    parser.add_argument("--vault", type=str, default="", help="Obsidian vault path")
    parser.add_argument("--channel", action="append", default=[], help="Channel id (repeatable)")
    parser.add_argument("--url", action="append", default=[], help="Web page URL (repeatable)")
    parser.add_argument("--feed", action="append", default=[], help="RSS feed URL (repeatable)")
    parser.add_argument("--pubmed", type=str, default="", help="PubMed query override")
    parser.add_argument("--wechat-account", type=str, default="", help="WeChat official account name")
    parser.add_argument(
        "--wechat-url",
        action="append",
        default=[],
        help="WeChat article URL (repeatable)",
    )
    parser.add_argument("--no-media", action="store_true", help="Skip media download")
    args = parser.parse_args(argv)

    init_db()
    settings = get_settings()

    if args.job:
        job_path = Path(args.job).expanduser()
        if not job_path.is_absolute():
            job_path = (Path.cwd() / job_path).resolve()
        data = yaml.safe_load(job_path.read_text(encoding="utf-8")) or {}
        payload = CollectRequest(
            title=data.get("title") or "",
            topic=data.get("topic") or "",
            vault_path=data.get("vault_path") or args.vault or settings.default_vault_path,
            channel_ids=data.get("channel_ids"),
            urls=list(data.get("urls") or []),
            feeds=list(data.get("feeds") or []),
            pubmed_query=data.get("pubmed_query"),
            wechat_account=data.get("wechat_account"),
            wechat_urls=list(data.get("wechat_urls") or []),
            download_media=not data.get("no_media", False),
            scope=ScopeSpec.model_validate(data["scope"]) if data.get("scope") else None,
        )
    else:
        if not args.topic:
            parser.error("--topic or --job is required")
        payload = CollectRequest(
            title=args.title,
            topic=args.topic,
            vault_path=args.vault or settings.default_vault_path,
            channel_ids=args.channel or None,
            urls=args.url,
            feeds=args.feed,
            pubmed_query=args.pubmed or None,
            wechat_account=args.wechat_account or None,
            wechat_urls=args.wechat_url,
            download_media=not args.no_media,
        )

    vault = payload.vault_path or str(PROJECT_ROOT / "vault")
    payload.vault_path = vault

    db = SessionLocal()
    try:
        result = run_collect(db, payload, vault_path=vault)
    finally:
        db.close()

    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
