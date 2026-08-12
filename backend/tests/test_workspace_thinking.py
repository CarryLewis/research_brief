"""Thinking vault: freeform notes under Thinking/ + human Notes preservation."""

from __future__ import annotations

from app.db import KnowledgeObject, Notebook, Reflection
from app.services import thinking as thinking_svc
from app.services import workspace as workspace_svc
from app.utils import new_id


def _notebook(db_session, vault_path):
    nb = Notebook(
        id=new_id("nb"),
        title="think",
        topic="thinking tests",
        vault_path=str(vault_path),
    )
    db_session.add(nb)
    db_session.commit()
    return nb


def test_reflection_render_is_freeform(db_session, vault_path):
    nb = _notebook(db_session, vault_path)
    ko, _ref = thinking_svc.create_reflection(
        db_session,
        notebook_id=nb.id,
        title="Morning notes",
        body_md="Connectivity feels over-indexed.\n\nNext: re-read MMN paper.",
        vault_path=str(vault_path),
        sync=True,
    )
    text = (vault_path / "Thinking" / "Morning notes.md").read_text(encoding="utf-8")
    assert "type: reflection" not in text  # minimal frontmatter
    assert "## Summary" not in text
    assert "## Key Ideas" not in text
    assert "## My Reflection" not in text
    assert "Connectivity feels over-indexed." in text
    assert "Next: re-read MMN paper." in text
    rendered = workspace_svc.render_workspace_note(db_session, ko)
    assert "## Summary" not in rendered
    assert "Connectivity feels over-indexed." in rendered


def test_sync_preserves_existing_reflection_file(db_session, vault_path):
    nb = _notebook(db_session, vault_path)
    ko, _ref = thinking_svc.create_reflection(
        db_session,
        notebook_id=nb.id,
        title="Keep my words",
        body_md="original api body",
        vault_path=str(vault_path),
        sync=True,
    )
    path = vault_path / "Thinking" / "Keep my words.md"
    path.write_text(
        "---\ntitle: \"Keep my words\"\ndate: 2026-08-02\n---\n\n"
        "# Keep my words\n\nI wrote this in Obsidian and it must survive sync.\n",
        encoding="utf-8",
    )
    workspace_svc.sync_note(db_session, ko, vault_path=str(vault_path), force=False)
    text = path.read_text(encoding="utf-8")
    assert "I wrote this in Obsidian and it must survive sync." in text
    assert "original api body" not in text


def test_concept_sync_preserves_notes_and_refreshes_summary(db_session, vault_path):
    nb = _notebook(db_session, vault_path)
    ko = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb.id,
        kind="concept",
        title="Migraine",
        summary="old summary",
        key_points_json='["point a"]',
        workspace_role="concept",
        lifecycle_stage="concept",
        graph_eligible=1,
        tags_json="[]",
        entities_json="[]",
        metadata_json="{}",
        content_hash="h1",
        connector="manual",
    )
    db_session.add(ko)
    db_session.commit()

    path = vault_path / "Thinking" / "Migraine.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\ntitle: \"Migraine\"\ndate: 2026-08-02\n---\n\n# Migraine\n\n"
        "## Summary\n\nold summary\n\n"
        "## Key Ideas\n\n- point a\n\n"
        "## Connections\n\n\n"
        "## Notes\n\nMy handwritten hypothesis about sensory load.\n\n"
        "## References\n\n\n",
        encoding="utf-8",
    )
    ko.vault_path = "Thinking/Migraine.md"
    ko.summary = "new machine summary"
    ko.key_points_json = '["point a", "point b"]'
    db_session.commit()

    workspace_svc.sync_note(db_session, ko, vault_path=str(vault_path))
    text = path.read_text(encoding="utf-8")
    assert "new machine summary" in text
    assert "point b" in text
    assert "My handwritten hypothesis about sensory load." in text
    assert "## Notes" in text
    assert "## My Reflection" not in text
    assert "## Open Questions" not in text


def test_extract_human_notes_prefers_notes_over_legacy_reflection():
    md = (
        "## Notes\n\nkeep me\n\n"
        "## My Reflection\n\nlegacy\n\n"
        "## References\n\n"
    )
    assert workspace_svc.extract_human_notes(md) == "keep me"

    legacy_only = "## My Reflection\n\nlegacy only\n\n## References\n\n"
    assert workspace_svc.extract_human_notes(legacy_only) == "legacy only"
