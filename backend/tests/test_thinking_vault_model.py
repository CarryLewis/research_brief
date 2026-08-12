"""Canonical Thinking Object + markdown contract tests (no Notion network)."""

from __future__ import annotations

import pytest

from app.services.thinking_vault import (
    ConnectionRef,
    ThinkingObject,
    normalize_thinking_properties,
    render_thinking_markdown,
    thinking_content_hash,
)


def test_normalize_requires_identity():
    with pytest.raises(ValueError, match="source_id"):
        normalize_thinking_properties({"title": "x"})
    with pytest.raises(ValueError, match="title"):
        normalize_thinking_properties({"source_id": "abc"})


def test_normalize_questions_newline_split_and_connections():
    obj = normalize_thinking_properties(
        {
            "title": "Dizziness is not Vertigo",
            "source_id": "page-1",
            "status": "Active",
            "raw_thought": "夜班后头晕…",
            "questions": "Is this orthostatic?\n\nWhat did the patient mean by dizzy?",
            "connections": [
                {"title": "Clinical communication", "source_id": "page-2"},
                "Bare title link",
            ],
        }
    )
    assert obj.questions == [
        "Is this orthostatic?",
        "What did the patient mean by dizzy?",
    ]
    assert [c.title for c in obj.connections] == [
        "Clinical communication",
        "Bare title link",
    ]
    assert obj.connections[0].source_id == "page-2"
    assert obj.should_write_active()
    assert not obj.should_skip_sync()


def test_status_draft_skips_active_archive():
    draft = normalize_thinking_properties(
        {"title": "t", "source_id": "1", "status": "Draft", "raw_thought": "x"}
    )
    assert draft.should_skip_sync()
    assert not draft.should_write_active()

    archived = normalize_thinking_properties(
        {"title": "t", "source_id": "2", "status": "Archived"}
    )
    assert archived.should_archive()
    assert not archived.should_write_active()

    empty = normalize_thinking_properties({"title": "t", "source_id": "3"})
    assert empty.should_write_active()


def test_render_omits_empty_sections_preserves_raw_thought():
    obj = ThinkingObject(
        title="Dizziness is not Vertigo",
        source_id="abc123",
        created_at="2026-08-12",
        updated_at="2026-08-12",
        raw_thought="今天夜班……",
        interpretation="不是真性眩晕。",
        context="",  # omitted
        connections=[ConnectionRef(title="Clinical communication", source_id="p2")],
    )
    md = render_thinking_markdown(obj)
    assert md.startswith("---\n")
    assert "source: notion" in md
    assert "source_id: abc123" in md
    assert "# Dizziness is not Vertigo" in md
    assert "## Raw Thought" in md
    assert "今天夜班……" in md
    assert "## Interpretation" in md
    assert "## Connections" in md
    assert "[[Clinical communication]]" in md
    assert "## Context" not in md
    assert "## Observation" not in md
    assert "## Questions" not in md


def test_raw_thought_never_dropped_when_present():
    obj = normalize_thinking_properties(
        {
            "title": "Keep raw",
            "source_id": "r1",
            "raw_thought": "human voice must survive",
            "interpretation": "AI structure ok",
        }
    )
    md = render_thinking_markdown(obj)
    assert "## Raw Thought" in md
    assert "human voice must survive" in md
    # Raw Thought section appears before Interpretation
    assert md.index("## Raw Thought") < md.index("## Interpretation")


def test_content_hash_stable_and_changes_on_edit():
    a = normalize_thinking_properties(
        {
            "title": "Same",
            "source_id": "id-1",
            "raw_thought": "one",
            "connections": [{"title": "A", "source_id": "x"}],
        }
    )
    b = normalize_thinking_properties(
        {
            "title": "Same",
            "source_id": "id-1",
            "raw_thought": "one",
            "connections": [{"title": "A", "source_id": "x"}],
        }
    )
    c = normalize_thinking_properties(
        {
            "title": "Same",
            "source_id": "id-1",
            "raw_thought": "two",
            "connections": [{"title": "A", "source_id": "x"}],
        }
    )
    assert thinking_content_hash(a) == thinking_content_hash(b)
    assert thinking_content_hash(a) != thinking_content_hash(c)


def test_identity_is_source_id_not_title():
    renamed = normalize_thinking_properties(
        {
            "title": "New Title",
            "source_id": "stable-id",
            "raw_thought": "same body",
        }
    )
    assert renamed.source_id == "stable-id"
    assert renamed.title == "New Title"
