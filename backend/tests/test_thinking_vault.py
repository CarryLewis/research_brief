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
    format_context_wikilinks,
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
    context: str = "",
    tags: list[str] | None = None,
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
        "Context": {
            "id": "ctx",
            "type": "rich_text",
            "rich_text": _rich(context) if context else [],
        },
        "Observation": {"id": "obs", "type": "rich_text", "rich_text": []},
        "Interpretation": {
            "id": "interp",
            "type": "rich_text",
            "rich_text": _rich(interpretation) if interpretation else [],
        },
        "Uncertainty": {"id": "unc", "type": "rich_text", "rich_text": []},
        "Questions": {"id": "q", "type": "rich_text", "rich_text": []},
        "Later Reflection": {"id": "later", "type": "rich_text", "rich_text": []},
        "Tags": {
            "id": "tags",
            "type": "multi_select",
            "multi_select": [{"name": t} for t in (tags or [])],
        },
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


def test_format_context_wikilinks():
    assert (
        format_context_wikilinks("Clinical communication；Vestibular language")
        == "[[Clinical communication]]; [[Vestibular language]]"
    )
    assert format_context_wikilinks("[[Already Linked]]; New Topic") == (
        "[[Already Linked]]; [[New Topic]]"
    )
    assert format_context_wikilinks("") == ""


def test_render_markdown_omits_empty_sections_and_keeps_raw():
    obj = ThinkingObject(
        title="Dizziness is not Vertigo",
        source_id="abc123",
        created_at="2026-08-12T09:00:00.000Z",
        updated_at="2026-08-12T10:00:00.000Z",
        raw_thought="今天夜班……",
        context="Clinical communication；Patient language of dizziness",
        interpretation="Not vertigo.",
        page_body="更细致的反思：患者用词与我的临床分类可能错位。",
        connections=[ThinkingConnection(title="Clinical communication")],
    )
    md = render_markdown(obj)
    assert 'source_id: "abc123"' in md
    assert "## Raw Thought" in md
    assert "今天夜班……" in md
    assert "## Context" in md
    assert "[[Clinical communication]]; [[Patient language of dizziness]]" in md
    assert "## Interpretation" in md
    assert "## Extended Reflection" in md
    assert "更细致的反思" in md
    assert md.index("## Extended Reflection") < md.index("## Connections")
    assert "[[Clinical communication]]" in md
    assert "## Connections" in md
    # Empty tags → no footer hash-tags, and Context stays wikilinks only
    assert "#medicine" not in md
    assert "## Tags" not in md


def test_normalize_and_render_tags_at_page_bottom():
    page = _page(
        "11111111-1111-1111-1111-111111111111",
        "Dizziness is not Vertigo",
        raw="今天夜班……",
        context="Clinical communication；Patient language of dizziness",
        tags=["Medicine", "neurology", "paper", "clinical", "todo", "review", "extra"],
        relations=["22222222-2222-2222-2222-222222222222"],
    )
    obj = normalize_page(
        page,
        relation_titles={
            "22222222-2222-2222-2222-222222222222": "Clinical communication",
        },
    )
    assert obj.tags == ["medicine", "neurology", "clinical", "todo", "review"]
    assert "paper" not in obj.tags  # type tags rejected
    assert "tags:medicine,neurology,clinical,todo,review" in obj.content_fingerprint()

    md = render_markdown(obj)
    assert "## Context" in md
    assert "[[Clinical communication]]; [[Patient language of dizziness]]" in md
    assert "#Clinical communication" not in md  # Context ≠ hashtag
    assert "## Tags" not in md
    assert md.rstrip().endswith("#medicine #neurology #clinical #todo #review")
    assert md.index("## Connections") < md.index("#medicine #neurology")


def test_empty_tags_omit_footer_and_hash_changes_with_tags():
    bare = ThinkingObject(
        title="t",
        source_id="1",
        raw_thought="x",
        context="Night shift clinical reasoning",
    )
    tagged = ThinkingObject(
        title="t",
        source_id="1",
        raw_thought="x",
        context="Night shift clinical reasoning",
        tags=["neurology"],
    )
    bare_md = render_markdown(bare)
    tagged_md = render_markdown(tagged)
    assert "#neurology" not in bare_md
    assert bare_md.rstrip().endswith("[[Night shift clinical reasoning]]")
    assert tagged_md.rstrip().endswith("#neurology")
    assert bare.content_fingerprint() != tagged.content_fingerprint()


def test_blocks_to_markdown_basic():
    from app.services.thinking_vault.blocks import blocks_to_markdown

    blocks = [
        {
            "type": "paragraph",
            "paragraph": {"rich_text": _rich("第一段详细反思。")},
        },
        {
            "type": "heading_2",
            "heading_2": {"rich_text": _rich("进一步观察")},
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _rich("条目一")},
        },
    ]
    md = blocks_to_markdown(blocks)
    assert "第一段详细反思。" in md
    assert "## 进一步观察" in md
    assert "- 条目一" in md


def test_normalize_includes_page_body():
    page = _page(
        "11111111-1111-1111-1111-111111111111",
        "Demo",
        raw="raw",
    )
    obj = normalize_page(page, page_body="详细正文")
    assert obj.page_body == "详细正文"
    assert "详细正文" in obj.content_fingerprint()


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


def test_hydrate_sync_state_from_vault_enables_rename(db_session, vault_path: Path):
    from app.db import ThinkingSyncState
    from app.services.thinking_vault.sync import hydrate_sync_state_from_vault
    from app.services.thinking_vault.writer import FOLDER_SIDECAR, write_thinking_folder

    note = ThinkingObject(
        title="Cold Start Note",
        source_id="hydrate-note-1",
        raw_thought="seed",
        updated_at="2026-08-12T10:00:00.000Z",
    )
    folder = ThinkingObject(
        title="Cold Start Folder",
        source_id="hydrate-folder-1",
        status="folder",
        updated_at="2026-08-12T10:00:00.000Z",
    )
    # Write files without any SQLite rows (simulates Actions cache miss).
    write_thinking_note(vault_path, note)
    write_thinking_folder(vault_path, folder)
    assert db_session.get(ThinkingSyncState, "hydrate-note-1") is None

    seeded = hydrate_sync_state_from_vault(db_session, vault_path)
    assert seeded >= 2
    note_row = db_session.get(ThinkingSyncState, "hydrate-note-1")
    folder_row = db_session.get(ThinkingSyncState, "hydrate-folder-1")
    assert note_row is not None and note_row.status == "active"
    assert folder_row is not None and folder_row.status == "active"
    assert (vault_path / folder_row.vault_path / FOLDER_SIDECAR).is_file()

    # Empty DB again, then apply rename via hydrated previous path.
    db_session.delete(note_row)
    db_session.delete(folder_row)
    db_session.commit()
    note.title = "Renamed After Hydrate"
    note.updated_at = "2026-08-12T11:00:00.000Z"
    result = apply_thinking_objects(db_session, [note, folder], vault_path=str(vault_path))
    assert result.errors == []
    assert (vault_path / "Thinking" / "Renamed After Hydrate.md").is_file()
    assert not (vault_path / "Thinking" / "Cold Start Note.md").exists()


def test_folder_status_fingerprint_ignores_body_props():
    folder = ThinkingObject(
        title="Clinical themes",
        source_id="folder-1",
        status="folder",
        raw_thought="AI writing style notes — Notion only",
        interpretation="should not affect hash",
        page_body="long guidance",
        tags=["medicine"],
        connections=[ThinkingConnection(title="Alpha", source_id="id-a")],
    )
    assert folder.is_folder()
    fp1 = folder.content_fingerprint()
    folder.raw_thought = "changed"
    folder.page_body = "also changed"
    folder.tags = ["neurology"]
    assert folder.content_fingerprint() == fp1
    folder.connections = [
        ThinkingConnection(title="Alpha", source_id="id-a"),
        ThinkingConnection(title="Beta", source_id="id-b"),
    ]
    assert folder.content_fingerprint() != fp1


def test_folder_create_move_rename_multi_owner_and_archive(db_session, vault_path: Path):
    from app.services.thinking_vault.writer import FOLDER_SIDECAR

    folder = ThinkingObject(
        title="Vertigo cluster",
        source_id="folder-1",
        status="folder",
        raw_thought="Notion-only style guide",
        updated_at="2026-08-12T10:00:00.000Z",
        connections=[
            ThinkingConnection(title="Alpha", source_id="id-a"),
            ThinkingConnection(title="Beta", source_id="id-b"),
        ],
    )
    other = ThinkingObject(
        title="Another cluster",
        source_id="folder-2",
        status="folder",
        updated_at="2026-08-12T10:00:00.000Z",
        connections=[ThinkingConnection(title="Alpha", source_id="id-a")],
    )
    a = ThinkingObject(
        title="Alpha",
        source_id="id-a",
        raw_thought="a",
        updated_at="2026-08-12T10:00:00.000Z",
    )
    b = ThinkingObject(
        title="Beta",
        source_id="id-b",
        raw_thought="b",
        updated_at="2026-08-12T10:00:00.000Z",
    )

    r1 = apply_thinking_objects(
        db_session, [folder, other, a, b], vault_path=str(vault_path)
    )
    assert r1.folders == 2
    assert any("claimed by multiple folders" in w for w in r1.warnings)
    # Lexicographically smallest folder title wins: "Another cluster" < "Vertigo cluster"
    alpha = vault_path / "Thinking" / "Another cluster" / "Alpha.md"
    beta = vault_path / "Thinking" / "Vertigo cluster" / "Beta.md"
    assert alpha.is_file()
    assert beta.is_file()
    assert (vault_path / "Thinking" / "Another cluster" / FOLDER_SIDECAR).is_file()
    assert not (vault_path / "Thinking" / "Alpha.md").exists()
    # Folder page body/props must not become a note
    assert not (vault_path / "Thinking" / "Vertigo cluster.md").exists()
    assert "Notion-only" not in beta.read_text(encoding="utf-8")

    # Rename folder + remove Alpha membership from Vertigo (still in Another)
    folder.title = "Vestibular cluster"
    folder.connections = [ThinkingConnection(title="Beta", source_id="id-b")]
    folder.updated_at = "2026-08-12T11:00:00.000Z"
    r2 = apply_thinking_objects(
        db_session, [folder, other, a, b], vault_path=str(vault_path)
    )
    assert r2.renamed >= 1 or (vault_path / "Thinking" / "Vestibular cluster").is_dir()
    assert (vault_path / "Thinking" / "Vestibular cluster" / "Beta.md").is_file()
    assert not (vault_path / "Thinking" / "Vertigo cluster").exists()

    # Remove Alpha from all folders → back to Thinking root
    other.connections = []
    other.updated_at = "2026-08-12T12:00:00.000Z"
    r3 = apply_thinking_objects(
        db_session, [folder, other, a, b], vault_path=str(vault_path)
    )
    assert (vault_path / "Thinking" / "Alpha.md").is_file()
    assert not (vault_path / "Thinking" / "Another cluster" / "Alpha.md").exists()
    assert r3.errors == []

    # Soft-archive missing folder page
    r4 = apply_thinking_objects(db_session, [other, a, b], vault_path=str(vault_path))
    assert r4.archived >= 1
    archived_dirs = [
        p for p in (vault_path / "Archive" / "Thinking").iterdir() if p.is_dir()
    ]
    assert archived_dirs


def test_nested_folder_membership(db_session, vault_path: Path):
    parent = ThinkingObject(
        title="Parent theme",
        source_id="folder-parent",
        status="folder",
        updated_at="2026-08-12T10:00:00.000Z",
        connections=[ThinkingConnection(title="Child theme", source_id="folder-child")],
    )
    child = ThinkingObject(
        title="Child theme",
        source_id="folder-child",
        status="folder",
        updated_at="2026-08-12T10:00:00.000Z",
        connections=[ThinkingConnection(title="Leaf", source_id="id-leaf")],
    )
    leaf = ThinkingObject(
        title="Leaf",
        source_id="id-leaf",
        raw_thought="nested",
        updated_at="2026-08-12T10:00:00.000Z",
    )
    result = apply_thinking_objects(
        db_session, [parent, child, leaf], vault_path=str(vault_path)
    )
    assert result.errors == []
    nested = vault_path / "Thinking" / "Parent theme" / "Child theme" / "Leaf.md"
    assert nested.is_file()
    assert "nested" in nested.read_text(encoding="utf-8")


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
        path = request.url.path
        if path.endswith("/databases/dddddddd-dddd-dddd-dddd-dddddddddddd/query"):
            return httpx.Response(
                200,
                json={"results": [page_a, page_b], "has_more": False, "next_cursor": None},
            )
        if "/blocks/" in path and path.endswith("/children"):
            page_id = path.split("/blocks/")[1].split("/children")[0]
            if page_id.startswith("aaaaaaaa"):
                results = [
                    {
                        "object": "block",
                        "id": "block-1",
                        "type": "paragraph",
                        "has_children": False,
                        "paragraph": {
                            "rich_text": _rich("夜班里我对头晕/vertigo 的错位感写得更细。")
                        },
                    }
                ]
            else:
                results = []
            return httpx.Response(
                200,
                json={"results": results, "has_more": False, "next_cursor": None},
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
    assert "错位感" in night.page_body
    assert night.connections[0].title == "Clinical communication"

    result = apply_thinking_objects(db_session, objects, vault_path=str(vault_path))
    assert result.created == 2
    md = (vault_path / "Thinking" / "Night Shift Observation.md").read_text(encoding="utf-8")
    assert "[[Clinical communication]]" in md
    assert "## Raw Thought" in md
    assert "## Extended Reflection" in md
    assert "错位感" in md
