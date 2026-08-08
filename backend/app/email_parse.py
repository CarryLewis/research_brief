"""HTML / URL helpers for inbound newsletter email."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse, urlunparse

# Tracking / unsubscribe / asset hosts and path fragments to drop
_SKIP_HOST_PARTS = (
    "unsubscribe",
    "list-manage",
    "mailchimp",
    "mandrillapp",
    "sendgrid.net",
    "click.",
    "track.",
    "links.iterable",
    "cdn.",
    "img.",
    "static.",
    "fonts.",
    "google-analytics",
    "doubleclick",
)

_SKIP_PATH_PARTS = (
    "unsubscribe",
    "optout",
    "opt-out",
    "email-preferences",
    "manage-subscription",
    "/track/",
    "/click/",
    "/open/",
)

_ARTICLE_PATH_HINTS = (
    "/p/",
    "/posts/",
    "/post/",
    "/article/",
    "/articles/",
    "/news/",
    "/blog/",
    "/stories/",
    "/s/",
    "/n/",
)

_URL_RE = re.compile(
    r"""(?xi)
    (?:
      href\s*=\s*['"]([^'"]+)['"]
      |
      (https?://[^\s<>'"\)\]]+)
    )
    """
)


def strip_html(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", text)
    text = re.sub(r"(?s)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)</p>", "\n\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def email_body_text(*, text: str | None, html: str | None) -> str:
    if text and text.strip():
        return text.strip()
    if html and html.strip():
        return strip_html(html)
    return ""


def normalize_url(url: str) -> str | None:
    url = (url or "").strip()
    if not url or url.startswith("#") or url.lower().startswith("mailto:"):
        return None
    if url.startswith("//"):
        url = "https:" + url
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    cleaned = parsed._replace(fragment="")
    return urlunparse(cleaned)


def _should_skip(url: str) -> bool:
    lower = url.lower()
    host = urlparse(lower).netloc
    path = urlparse(lower).path
    if any(p in host for p in _SKIP_HOST_PARTS):
        return True
    if any(p in path for p in _SKIP_PATH_PARTS):
        return True
    if path.endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".ico", ".woff", ".woff2")
    ):
        return True
    return False


def extract_urls(*, text: str | None = None, html: str | None = None) -> list[str]:
    blob = "\n".join(x for x in (html or "", text or "") if x)
    found: list[str] = []
    seen: set[str] = set()
    for m in _URL_RE.finditer(blob):
        raw = m.group(1) or m.group(2) or ""
        url = normalize_url(raw)
        if not url or _should_skip(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        found.append(url)
    return found


def _score_url(url: str, *, sender_domain: str | None, position: int, total: int) -> float:
    parsed = urlparse(url)
    path = parsed.path or "/"
    score = 0.0
    if total > 0:
        score += max(0.0, 1.0 - (position / max(total, 1))) * 2.0
    for hint in _ARTICLE_PATH_HINTS:
        if hint in path.lower():
            score += 3.0
            break
    if path not in {"", "/"} and len(path) > 1:
        score += 1.0
    if path.count("/") >= 2:
        score += 0.5
    if sender_domain:
        host = parsed.netloc.lower().removeprefix("www.")
        sd = sender_domain.lower().removeprefix("www.")
        if host == sd or host.endswith("." + sd) or sd.endswith("." + host):
            score += 2.0
    if path in {"", "/"}:
        score -= 2.0
    if "utm_" in (parsed.query or ""):
        score += 0.2
    return score


def sender_domain_from_address(sender: str) -> str | None:
    m = re.search(r"@([A-Za-z0-9.-]+)", sender or "")
    if not m:
        return None
    return m.group(1).lower().strip(".")


def select_article_urls(
    urls: list[str],
    *,
    max_links: int = 3,
    sender: str | None = None,
) -> list[str]:
    if not urls or max_links <= 0:
        return []
    domain = sender_domain_from_address(sender or "")
    ranked = sorted(
        enumerate(urls),
        key=lambda pair: _score_url(
            pair[1], sender_domain=domain, position=pair[0], total=len(urls)
        ),
        reverse=True,
    )
    out: list[str] = []
    seen_hosts_paths: set[str] = set()
    non_home = [u for _, u in ranked if (urlparse(u).path or "/").rstrip("/") != ""]
    pool = non_home if non_home else [u for _, u in ranked]
    for url in pool:
        parsed = urlparse(url)
        key = f"{parsed.netloc}{parsed.path}".rstrip("/").lower()
        if key in seen_hosts_paths:
            continue
        seen_hosts_paths.add(key)
        out.append(url)
        if len(out) >= max_links:
            break
    return out
