from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..schemas import CollectRequest, CollectResult, NotebookCreate, ScopeSpec
from ..utils import loads, workspace_config_dict
from . import analyze as analyze_svc
from . import ingest as ingest_svc
from . import llm as llm_svc
from . import notebook as notebook_svc
from . import workspace as workspace_svc


def run_collect(db: Session, payload: CollectRequest, vault_path: str) -> CollectResult:
    topic = payload.topic.strip()
    if not topic:
        raise ValueError("topic is required")

    title = (payload.title or topic).strip()
    scope = payload.scope or ScopeSpec(topic=topic)
    scope.topic = topic

    connectors = scope.connectors.model_copy(deep=True)
    if payload.urls:
        connectors.web.urls = list(dict.fromkeys([*connectors.web.urls, *payload.urls]))
    if payload.feeds:
        connectors.rss.feeds = list(dict.fromkeys([*connectors.rss.feeds, *payload.feeds]))
    if payload.wechat_urls:
        connectors.wechat.urls = list(
            dict.fromkeys([*connectors.wechat.urls, *payload.wechat_urls])
        )
    if payload.wechat_account:
        connectors.wechat.account = payload.wechat_account
    if payload.pubmed_query:
        connectors.pubmed.query = payload.pubmed_query
    elif not connectors.pubmed.query:
        connectors.pubmed.query = topic
    scope.connectors = connectors

    channel_ids = payload.channel_ids
    if channel_ids is None:
        if payload.urls or payload.feeds or payload.wechat_urls or payload.wechat_account:
            channel_ids = []
        else:
            channel_ids = list(scope.selected_channels or [])

    if payload.urls and "web" not in (scope.source_types or []):
        scope.source_types = list({*scope.source_types, "web"})
    if payload.feeds and "rss" not in (scope.source_types or []):
        scope.source_types = list({*scope.source_types, "rss"})
    if (payload.wechat_urls or payload.wechat_account) and "wechat" not in (
        scope.source_types or []
    ):
        scope.source_types = list({*scope.source_types, "wechat"})

    scope.selected_channels = channel_ids

    nb = notebook_svc.create_notebook(
        db,
        NotebookCreate(
            title=title,
            topic=topic,
            scope=scope,
            vault_path=vault_path,
        ),
    )
    notebook = notebook_svc.get_notebook(db, nb.id)
    assert notebook is not None

    sources, _fetched, added, skipped, failed = ingest_svc.ingest_from_scope(
        db,
        notebook.id,
        loads(notebook.scope_json, {}),
        channel_ids=channel_ids,
        store_media=payload.download_media,
    )

    # Distill into Knowledge Database when LLM is configured (not into Obsidian)
    if sources and llm_svc.is_configured():
        analysis_cfg = loads(notebook.analysis_json, {}) or {}
        lang = analysis_cfg.get("output_language") or get_settings().digest_language or "zh"
        from ..db import SourceDoc

        rows = (
            db.query(SourceDoc)
            .filter(SourceDoc.id.in_([s.id for s in sources]))
            .all()
        )
        analyze_svc.analyze_sources(db, rows, output_language=lang)

    # Constitution: Resources stay in DB. Only scaffold the Research Workspace.
    vault = Path(vault_path).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    cfg = workspace_config_dict()
    if cfg.get("scaffold_folders", True):
        workspace_svc.ensure_scaffold(vault, cfg)
    notebook.vault_path = str(vault)
    db.commit()

    return CollectResult(
        notebook_id=notebook.id,
        topic=topic,
        added=added,
        skipped_duplicates=skipped,
        failed=failed,
        vault_path=str(vault),
        index_path=str(vault),
        sources_written=0,  # no Obsidian notes from capture
    )
