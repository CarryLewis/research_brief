from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.db import Notebook, SourceDoc
from app.schemas import CollectRequest
from app.services import knowledge as knowledge_svc
from app.services import obsidian as obsidian_svc
from app.services import workspace as workspace_svc
from app.services.collect import run_collect
from app.utils import new_id


def test_folder_for_role():
    assert workspace_svc.folder_for_role("book") == "Books"
    assert workspace_svc.folder_for_role("concept") == "Concepts"
    assert workspace_svc.folder_for_role("project") == "Projects"


def test_export_resources_is_noop(db_session, vault_path):
    nb = Notebook(id=new_id("nb"), title="t", topic="topic", vault_path=str(vault_path))
    db_session.add(nb)
    src = SourceDoc(
        id=new_id("src"),
        notebook_id=nb.id,
        connector="web",
        title="Clean Note",
        url="https://example.com/c",
        raw_text="raw payload stays in lake",
        content_hash="h3",
        status="ready",
        metadata_json="{}",
    )
    db_session.add(src)
    db_session.commit()
    knowledge_svc.upsert_from_source(db_session, src)

    result = obsidian_svc.export_knowledge_objects(
        db_session, nb, vault_path=str(vault_path), source_ids=[src.id]
    )
    assert result.sources_written == 0
    assert not list((vault_path / "Concepts").glob("*.md"))
    assert not (vault_path / "Knowledge" / "Inbox").exists()


def test_collect_does_not_write_inbox_notes(db_session, vault_path, monkeypatch):
    # Avoid network: stub ingest to return empty docs after creating nothing
    from app.services import collect as collect_svc
    from app.services import ingest as ingest_svc

    def fake_ingest(db, notebook_id, scope, connectors=None, channel_ids=None, store_media=True):
        src = SourceDoc(
            id=new_id("src"),
            notebook_id=notebook_id,
            connector="pubmed",
            title="Fake Migraine Paper",
            url="https://pubmed.ncbi.nlm.nih.gov/1/",
            raw_text="Abstract about migraine mechanisms.",
            content_hash=new_id("h"),
            status="ready",
            metadata_json="{}",
        )
        db.add(src)
        db.commit()
        db.refresh(src)
        knowledge_svc.upsert_from_source(db, src, store_lake=True, store_media=False)
        from app.services.ingest import source_to_out

        return [source_to_out(src)], [], 1, 0, 0

    monkeypatch.setattr(ingest_svc, "ingest_from_scope", fake_ingest)
    monkeypatch.setattr(collect_svc.llm_svc, "is_configured", lambda: False)

    result = run_collect(
        db_session,
        CollectRequest(topic="migraine test", channel_ids=[]),
        vault_path=str(vault_path),
    )
    assert result.added == 1
    assert result.sources_written == 0
    assert not list(vault_path.rglob("Fake Migraine Paper.md"))
    # Scaffold exists
    assert (vault_path / "Concepts").is_dir()
    assert (vault_path / "Projects").is_dir()


def test_write_report_off_graph(vault_path):
    end = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    daily = workspace_svc.write_report_note(
        vault_path=str(vault_path),
        period="daily",
        content_md="# 每日快报\n\n要点…",
        period_end=end,
        subject="每日快报",
    )
    weekly = workspace_svc.write_report_note(
        vault_path=str(vault_path),
        period="weekly",
        content_md="# 每周快报\n\n要点…",
        period_end=end,
        subject="每周快报",
    )
    assert daily.endswith("Reports/Daily/2026-08-01.md")
    assert "W" in Path(weekly).name
    text = Path(daily).read_text(encoding="utf-8")
    assert "type: report" in text
    assert "graph: false" in text
