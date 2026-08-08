from __future__ import annotations

from pathlib import Path

import httpx
import yaml

from app.services import library_writer as lib
from tests.test_readable import SAMPLE_ARTICLE_HTML


def test_ensure_library_scaffold(vault_path: Path):
    root = lib.ensure_library_scaffold(vault_path)
    assert (root / "Library" / "Articles").is_dir()
    assert (root / "Library" / "Emails").is_dir()
    assert (root / "Library" / "Books").is_dir()
    assert (root / "Library" / "Attachments").is_dir()
    assert (root / "Library" / "Notes").is_dir()


def test_write_article_creates_product_v1_note(vault_path: Path):
    item = lib.LibraryItem(
        title="Migraine Pathways Explained",
        body_md="Migraine is more than a headache.\n\n![map](../Attachments/lib_x/brain.png)",
        canonical_url="https://example.com/articles/migraine-pathways",
        authors=["Ada Lovelace"],
        tags=["migraine"],
        item_id="lib_x",
        highlights=["Aura often precedes pain."],
        notes_md="Follow up with clinician notes.",
    )
    result = lib.write_article(vault_path, item)

    assert result.created is True
    assert result.note_relpath == "Library/Articles/Migraine Pathways Explained.md"
    assert result.note_path.is_file()
    assert result.attachments_dir == vault_path / "Library" / "Attachments" / "lib_x"

    text = result.note_path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    meta, body = text.split("---\n", 2)[1], text.split("---\n", 2)[2]
    data = yaml.safe_load(meta)
    assert data["id"] == "lib_x"
    assert data["type"] == "article"
    assert data["source_url"] == "https://example.com/articles/migraine-pathways"
    assert data["authors"] == ["Ada Lovelace"]
    assert data["visibility"] == "private"
    assert data["status"] == "inbox"
    assert data["tags"] == ["migraine"]
    assert "captured_at" in data

    assert body.lstrip().startswith("# Migraine Pathways Explained\n")
    assert "Migraine is more than a headache." in body
    assert "## Highlights" in body
    assert "- Aura often precedes pain." in body
    assert "## Notes" in body
    assert "Follow up with clinician notes." in body


def test_write_article_dedupes_by_source_url_and_preserves_notes(vault_path: Path):
    first = lib.write_article(
        vault_path,
        lib.LibraryItem(
            title="Original Title",
            body_md="First body",
            canonical_url="https://example.com/a",
            notes_md="My private annotation",
            highlights=["Keep me"],
            item_id="lib_keep",
        ),
    )
    second = lib.write_article(
        vault_path,
        lib.LibraryItem(
            title="Updated Title",
            body_md="Second body with more detail",
            canonical_url="https://example.com/a",
        ),
        on_duplicate="update",
    )

    assert second.updated is True
    assert second.created is False
    assert second.item_id == "lib_keep"
    assert second.note_path == first.note_path

    text = second.note_path.read_text(encoding="utf-8")
    assert "Second body with more detail" in text
    assert "Updated Title" in text
    assert "My private annotation" in text
    assert "Keep me" in text


def test_write_article_skip_duplicate(vault_path: Path):
    lib.write_article(
        vault_path,
        lib.LibraryItem(
            title="Once",
            body_md="body",
            canonical_url="https://example.com/once",
            item_id="lib_once",
        ),
    )
    again = lib.write_article(
        vault_path,
        lib.LibraryItem(
            title="Twice",
            body_md="changed",
            canonical_url="https://example.com/once",
        ),
        on_duplicate="skip",
    )
    assert again.skipped is True
    text = again.note_path.read_text(encoding="utf-8")
    assert "Twice" not in text
    assert "body" in text


def test_write_article_from_html_downloads_images(vault_path: Path):
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"library-writer-png"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("brain-map.png"):
            return httpx.Response(200, content=png_bytes, headers={"content-type": "image/png"})
        return httpx.Response(404, text="missing")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        result = lib.write_article_from_html(
            vault_path,
            SAMPLE_ARTICLE_HTML,
            base_url="https://example.com/articles/migraine-pathways",
            download_images=True,
            client=client,
        )

    assert result.created is True
    assert result.images_downloaded == 1
    assert result.note_relpath.startswith("Library/Articles/")
    text = result.note_path.read_text(encoding="utf-8")
    assert f"../Attachments/{result.item_id}/" in text
    assert "https://example.com/images/brain-map.png" not in text
    assert "cortical events" in text
    assert "## Highlights" in text
    assert "## Notes" in text

    files = list(result.attachments_dir.glob("*"))
    assert len(files) == 1
    assert files[0].read_bytes() == png_bytes

    meta = yaml.safe_load(text.split("---\n", 2)[1])
    assert meta["type"] == "article"
    assert meta["source_url"] == "https://example.com/articles/migraine-pathways"
    assert meta["authors"] == ["Ada Lovelace"]
    assert meta["visibility"] == "private"


def test_write_article_from_html_skip_does_not_redownload(vault_path: Path):
    first = lib.write_article_from_html(
        vault_path,
        SAMPLE_ARTICLE_HTML,
        base_url="https://example.com/articles/migraine-pathways",
        download_images=False,
    )
    second = lib.write_article_from_html(
        vault_path,
        SAMPLE_ARTICLE_HTML.replace("Migraine Pathways Explained", "CHANGED"),
        base_url="https://example.com/articles/migraine-pathways",
        download_images=False,
        on_duplicate="skip",
    )
    assert first.created is True
    assert second.skipped is True
    assert "CHANGED" not in second.note_path.read_text(encoding="utf-8")
