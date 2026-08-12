"""Tests for Thinking Vault canonical model, normalizer, writer, and sync."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.services.thinking_vault.adapter import NotionThinkingAdapter
from app.services.thinking_vault.model import ThinkingConnection, ThinkingObject
from app.services.thinking_vault.normalizer import normalize_page, rich_text_to_plain
from app.services.thinking_vault.notion_client import NotionClient
from app.services.thinking_vault.sync import apply_thinking_objects
from app.services.thinking_vault.writer import (
    natural_stem,
    render_markdown,
    write_thinking_note,
)


def _rich(text: str) -> list[dict]:
    return [{"type": "text", "plain_text": text, "text": {"content": text}}]


def _page(
    page_id: str,
    title: str,
    *,
    raw: str = "",
    interpretation: str = "",
    relations: list[str] | None = None,
    edited: str = "2026-08-12T10:00:00.000Z",
    created: str = "2026-08-12T09:00:00.000Z",
    status: str = "developing",
) -> dict:
    props = {
        "Name": {"id": "title", "type": "title", "title": _rich(title)},
        "Status": {
            "id": "status",
            "type": "select",
            "select": {"name": status} if status else None,
        },
        "Raw Thought": {"id": "raw", "type": "rich_text", "rich_text": _rich(raw)},
        "Context": {"id": "ctx", "type": "rich_text", "rich_text": []},
        "Observation": {"id": "obs", "type": "rich_text", "rich_text": []},
        "Interpretation": {
            "id": "interp",
            "type": "rich_text",
            "rich_text": _rich(interpretation) if interpretation else [],
        },
        "Uncertainty": {"id": "unc", "type": "rich_text", "rich_text": []},
        "Questions": {"id": "q", "type": "rich_text", "rich_text": []},
        "Later Reflection": {"id": "later", "type": "rich_text", "rich_text": []},
        "Related Information": {
            "id": "rel",
            "type": "relation",
            "relation": [{"id": rid} for rid in (relations or [])],
        },
    }
    return {
        "object": "page",
        "id": page_id,
        "created_time": created,
        "last_edited_time": edited,
        "properties": props,
    }


def test_thinking_object_serialize_roundtrip():
    obj = ThinkingObject(
        title="Dizziness is not Vertigo",
        source_id="abc-123",
        raw_thought="今天夜班……",
        interpretation="Not classic vertigo.",
        connections=[ThinkingConnection(title="Clinical communication", source_id="c1")],
        status="developing",
    )
    data = obj.to_dict()
    restored = ThinkingObject.from_dict(data)
    assert restored.title == obj.title
    assert restored.source_id == obj.source_id
    assert restored.raw_thought == obj.raw_thought
    assert restored.connections[0].title == "Clinical communication"
    assert "今天夜班" in restored.content_fingerprint()


def test_rich_text_preserves_newlines():
    blocks = [
        {"plain_text": "line1\n", "text": {"content": "line1\n"}},
        {"plain_text": "line2", "text": {"content": "line2"}},
    ]
    assert rich_text_to_plain(blocks) == "line1\nline2"


def test_normalize_page_property_mapping_and_links():
    page = _page(
        "11111111-1111-1111-1111-111111111111",
        "Dizziness is not Vertigo",
        raw="今天夜班这个病人一直说头晕",
        interpretation="May not be vertigo.",
        relations=["22222222-2222-2222-2222-222222222222"],
    )
    obj = normalize_page(
        page,
        relation_titles={
            "22222222-2222-2222-2222-222222222222": "Clinical communication",
        },
    )
    assert obj.title == "Dizziness is not Vertigo"
    assert obj.raw_thought.startswith("今天夜班")
    assert obj.interpretation == "May not be vertigo."
    assert obj.context == ""
    assert obj.connections[0].title == "Clinical communication"
    assert obj.status == "developing"


def test_render_markdown_omits_empty_sections_and_keeps_raw():
    obj = ThinkingObject(
        title="Dizziness is not Vertigo",
        source_id="abc123",
        created_at="2026-08-12T09:00:00.000Z",
        updated_at="2026-08-12T10:00:00.000Z",
        raw_thought="今天夜班……",
        interpretation="Not vertigo.",
        connections=[ThinkingConnection(title="Clinical communication")],
    )
    md = render_markdown(obj)
    assert 'source_id: "abc123"' in md
    assert "## Raw Thought" in md
    assert "今天夜班……" in md
    assert "## Interpretation" in md
    assert "## Context" not in md
    assert "[[Clinical communication]]" in md
    assert "## Connections" in md


def test_writer_create_update_rename_idempotent(vault_path: Path):
    obj = ThinkingObject(
        title="Dizziness is not Vertigo",
        source_id="page-1",
        created_at="2026-08-12",
        updated_at="2026-08-12",
        raw_thought="raw-v1",
    )
    r1 = write_thinking_note(vault_path, obj)
    assert r1.action == "created"
    path = vault_path / r1.vault_path
    assert path.is_file()
    assert "raw-v1" in path.read_text(encoding="utf-8")

    r2 = write_thinking_note(
        vault_path,
        obj,
        previous_relpath=r1.vault_path,
        previous_hash=r1.content_hash,
    )
    assert r2.action == "unchanged"
    assert r2.vault_path == r1.vault_path

    obj.raw_thought = "raw-v2"
    obj.updated_at = "2026-08-13"
    r3 = write_thinking_note(
        vault_path,
        obj,
        previous_relpath=r1.vault_path,
        previous_hash=r1.content_hash,
    )
    assert r3.action == "updated"
    assert "raw-v2" in (vault_path / r3.vault_path).read_text(encoding="utf-8")

    obj.title = "Dizziness and Patient Language"
    r4 = write_thinking_note(
        vault_path,
        obj,
        previous_relpath=r3.vault_path,
        previous_hash=r3.content_hash,
    )
    assert r4.action == "renamed"
    assert not (vault_path / "Thinking" / "Dizziness is not Vertigo.md").exists()
    new_path = vault_path / r4.vault_path
    assert new_path.name == "Dizziness and Patient Language.md"
    assert 'source_id: "page-1"' in new_path.read_text(encoding="utf-8")


def test_natural_stem_strips_illegal_chars():
    assert "/" not in natural_stem("A/B:C*")
    assert natural_stem("A/B:C*") == "A-BC"


def test_sync_idempotent_and_archive(db_session, vault_path: Path):
    a = ThinkingObject(
        title="Alpha",
        source_id="id-a",
        raw_thought="a",
        updated_at="2026-08-12T10:00:00.000Z",
        connections=[ThinkingConnection(title="Beta", source_id="id-b")],
    )
    b = ThinkingObject(
        title="Beta",
        source_id="id-b",
        raw_thought="b",
        updated_at="2026-08-12T10:00:00.000Z",
    )
    r1 = apply_thinking_objects(db_session, [a, b], vault_path=str(vault_path))
    assert r1.created == 2
    alpha = vault_path / "Thinking" / "Alpha.md"
    assert "[[Beta]]" in alpha.read_text(encoding="utf-8")

    r2 = apply_thinking_objects(db_session, [a, b], vault_path=str(vault_path))
    assert r2.unchanged == 2
    assert r2.created == 0
    assert len(list((vault_path / "Thinking").glob("*.md"))) == 2

    # Rename target + refresh link titles in same batch
    b.title = "Beta Renamed"
    a.connections = [ThinkingConnection(title="Beta Renamed", source_id="id-b")]
    a.updated_at = "2026-08-12T11:00:00.000Z"
    b.updated_at = "2026-08-12T11:00:00.000Z"
    r3 = apply_thinking_objects(db_session, [a, b], vault_path=str(vault_path))
    assert r3.renamed >= 1 or r3.updated >= 1
    assert "[[Beta Renamed]]" in (vault_path / "Thinking" / "Alpha.md").read_text(
        encoding="utf-8"
    )

    # Soft-archive missing page
    r4 = apply_thinking_objects(db_session, [a], vault_path=str(vault_path))
    assert r4.archived == 1
    assert (vault_path / "Archive" / "Thinking").exists()
    archived = list((vault_path / "Archive" / "Thinking").glob("*.md"))
    assert archived


def test_adapter_with_mocked_notion(db_session, vault_path: Path):
    page_a = _page(
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "Night Shift Observation",
        raw="头晕",
        relations=["bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"],
    )
    page_b = _page(
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "Clinical communication",
        raw="language matters",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/databases/dddddddd-dddd-dddd-dddd-dddddddddddd/query"):
            return httpx.Response(
                200,
                json={"results": [page_a, page_b], "has_more": False, "next_cursor": None},
            )
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport,
        base_url="https://api.notion.com/v1",
        headers={
            "Authorization": "Bearer test",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
    ) as http:
        client = NotionClient("test-token", client=http)
        adapter = NotionThinkingAdapter(
            client,
            "dddddddddddddddddddddddddddddddd",
        )
        objects = adapter.fetch_thinking_objects()

    assert len(objects) == 2
    night = next(o for o in objects if o.title == "Night Shift Observation")
    assert night.raw_thought == "头晕"
    assert night.connections[0].title == "Clinical communication"

    result = apply_thinking_objects(db_session, objects, vault_path=str(vault_path))
    assert result.created == 2
    md = (vault_path / "Thinking" / "Night Shift Observation.md").read_text(encoding="utf-8")
    assert "[[Clinical communication]]" in md
    assert "## Raw Thought" in md
