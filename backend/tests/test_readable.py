from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.services import readable


SAMPLE_ARTICLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Migraine Pathways Explained | Science Daily</title>
  <meta name="author" content="Ada Lovelace"/>
  <meta name="description" content="A readable overview of migraine neural pathways."/>
  <link rel="canonical" href="https://example.com/articles/migraine-pathways"/>
</head>
<body>
  <header>
    <nav>
      <a href="/">Home</a>
      <a href="/login">Login</a>
      <ul>
        <li>Subscribe</li>
        <li>Advertisement sidebar filler text repeated for noise.</li>
      </ul>
    </nav>
  </header>
  <main>
    <article>
      <h1>Migraine Pathways Explained</h1>
      <p class="byline">By Ada Lovelace</p>
      <p>
        Migraine is more than a headache. Researchers describe cascading
        cortical events that begin with aura and continue through pain
        amplification in brainstem networks. This paragraph is intentionally
        long enough for readability heuristics to treat it as primary content
        rather than navigation chrome or promotional sidebar copy that sites
        commonly inject around the article column.
      </p>
      <p>
        Functional connectivity studies further suggest that sensory
        integration regions become hypersensitive during attacks. Clinicians
        therefore look beyond acute analgesics toward prevention strategies
        that dampen these recurrent network states over weeks and months.
      </p>
      <figure>
        <img src="/images/brain-map.png" alt="Brain connectivity map"/>
        <figcaption>Connectivity map during migraine aura.</figcaption>
      </figure>
      <h2>Key findings</h2>
      <ul>
        <li>Aura often precedes pain by minutes to an hour.</li>
        <li>Brainstem nuclei amplify nociceptive signals.</li>
        <li>Prevention can reduce attack frequency.</li>
      </ul>
      <p>
        For deeper reading, see the
        <a href="/papers/2024-review">2024 review paper</a>
        summarizing multisensory integration models.
      </p>
    </article>
  </main>
  <aside>
    <h3>Related ads</h3>
    <p>Buy vitamins now. Limited offer. Click here repeatedly.</p>
  </aside>
  <footer>
    <p>Copyright Example Media. Privacy policy. Terms of service.</p>
  </footer>
</body>
</html>
"""


def test_parse_html_extracts_title_and_markdown_structure():
    result = readable.parse_html(SAMPLE_ARTICLE_HTML, base_url="https://example.com/articles/migraine-pathways")

    assert "Migraine Pathways" in result.title
    assert "Science Daily" not in result.title
    assert result.byline == "Ada Lovelace"
    assert result.canonical_url == "https://example.com/articles/migraine-pathways"
    assert "Login" not in result.body_md
    assert "Buy vitamins" not in result.body_md
    assert "cortical events" in result.body_md
    assert "## Key findings" in result.body_md or "Key findings" in result.body_md
    assert "- Aura often precedes" in result.body_md or "Aura often precedes" in result.body_md
    assert "https://example.com/images/brain-map.png" in result.body_md
    assert "https://example.com/papers/2024-review" in result.body_md
    assert result.images and result.images[0].original_url.endswith("brain-map.png")


def test_parse_html_empty_input():
    result = readable.parse_html("   ")
    assert result.title == ""
    assert result.body_md == ""


def test_download_images_rewrites_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("brain-map.png"):
            return httpx.Response(200, content=png_bytes, headers={"content-type": "image/png"})
        return httpx.Response(404, text="missing")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        result = readable.parse_html(
            SAMPLE_ARTICLE_HTML,
            base_url="https://example.com/articles/migraine-pathways",
            download_images=True,
            image_dir=tmp_path / "attachments",
            image_path_prefix="Attachments/item1",
            client=client,
        )

    assert result.images
    img = result.images[0]
    assert img.error is None
    assert img.local_path is not None
    assert img.local_path.exists()
    assert img.local_path.read_bytes() == png_bytes
    assert img.markdown_path == f"Attachments/item1/{img.local_path.name}"
    assert "https://example.com/images/brain-map.png" not in result.body_md
    assert f"![{img.alt}]({img.markdown_path})" in result.body_md
    assert "cortical events" in result.body_md


def test_download_images_requires_image_dir():
    with pytest.raises(ValueError, match="image_dir"):
        readable.parse_html(SAMPLE_ARTICLE_HTML, download_images=True)


def test_parse_url_uses_fetched_html(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/articles/migraine-pathways"
        return httpx.Response(
            200,
            text=SAMPLE_ARTICLE_HTML,
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        result = readable.parse_url(
            "https://example.com/articles/migraine-pathways",
            client=client,
        )

    assert "Migraine Pathways" in result.title
    assert "cortical events" in result.body_md
    assert result.metadata.get("error") is None


def test_parse_url_invalid_scheme():
    result = readable.parse_url("ftp://example.com/x")
    assert result.body_md == ""
    assert "Invalid URL" in result.title
