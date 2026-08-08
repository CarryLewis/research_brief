from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_readable import SAMPLE_ARTICLE_HTML


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    data = tmp_path / "data"
    data.mkdir()

    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("DEFAULT_VAULT_PATH", str(vault))
    monkeypatch.setenv("LIBRARY_API_TOKEN", "test-library-token")
    monkeypatch.setenv("CONTENT_LAKE_DIR", str(tmp_path / "lake"))

    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as c:
        yield c, vault

    get_settings.cache_clear()


def test_library_save_requires_token(client):
    c, vault = client
    resp = c.post(
        "/api/library/save",
        json={
            "html": SAMPLE_ARTICLE_HTML,
            "url": "https://example.com/articles/migraine-pathways",
            "download_images": False,
        },
    )
    assert resp.status_code == 401


def test_library_save_html_writes_article(client):
    c, vault = client
    resp = c.post(
        "/api/library/save",
        headers={"Authorization": "Bearer test-library-token"},
        json={
            "html": SAMPLE_ARTICLE_HTML,
            "url": "https://example.com/articles/migraine-pathways",
            "tags": ["migraine"],
            "download_images": False,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["created"] is True
    assert data["item_id"].startswith("lib_")
    assert data["note_relpath"].startswith("Library/Articles/")
    assert data["source_url"] == "https://example.com/articles/migraine-pathways"
    assert "Migraine Pathways" in data["title"]

    note = Path(data["note_path"])
    assert note.is_file()
    text = note.read_text(encoding="utf-8")
    assert "cortical events" in text
    assert "visibility: private" in text
    assert "## Highlights" in text
    assert (vault / "Library" / "Articles").is_dir()


def test_library_save_body_md_and_x_library_token(client):
    c, vault = client
    resp = c.post(
        "/api/library/save",
        headers={"X-Library-Token": "test-library-token"},
        json={
            "title": "Pasted Note",
            "body_md": "Hello from markdown.",
            "url": "https://example.com/pasted",
            "download_images": False,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["created"] is True
    text = Path(data["note_path"]).read_text(encoding="utf-8")
    assert "Hello from markdown." in text
    assert "# Pasted Note" in text


def test_library_save_duplicate_skip(client):
    c, _vault = client
    headers = {"Authorization": "Bearer test-library-token"}
    payload = {
        "html": SAMPLE_ARTICLE_HTML,
        "url": "https://example.com/articles/migraine-pathways",
        "download_images": False,
    }
    first = c.post("/api/library/save", headers=headers, json=payload)
    assert first.status_code == 200
    second = c.post(
        "/api/library/save",
        headers=headers,
        json={**payload, "on_duplicate": "skip", "title": "Should Not Apply"},
    )
    assert second.status_code == 200
    data = second.json()
    assert data["skipped"] is True
    assert data["created"] is False
    assert "Should Not Apply" not in Path(data["note_path"]).read_text(encoding="utf-8")


def test_library_save_rejects_empty_payload(client):
    c, _vault = client
    resp = c.post(
        "/api/library/save",
        headers={"Authorization": "Bearer test-library-token"},
        json={},
    )
    assert resp.status_code == 400


def test_health_reports_library_auth(client):
    c, _vault = client
    resp = c.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "library-v1"
    assert data["library_auth_required"] is True
