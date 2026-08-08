"""WeChat official-account (公众号) connector.

WeChat does not expose a public article list/RSS API. This connector:
1. Fetches explicit ``mp.weixin.qq.com`` article URLs when provided
2. Best-effort discovers recent articles via Sogou WeChat search by account name

Pages often reject non-browser User-Agents with an environment-check interstitial;
we use a browser-like UA and extract ``#js_content``.
"""

from __future__ import annotations

import re
import time
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .base import BaseConnector, FetchedDoc, MediaAsset

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class WeChatConnector(BaseConnector):
    name = "wechat"

    def fetch(self, scope: dict[str, Any]) -> list[FetchedDoc]:
        cfg = (scope.get("connectors") or {}).get("wechat") or {}
        account = (cfg.get("account") or scope.get("topic") or "").strip()
        urls = [u.strip() for u in (cfg.get("urls") or []) if (u or "").strip()]
        max_articles = int(cfg.get("max_articles") or 5)
        discover = bool(cfg.get("discover", True))

        docs: list[FetchedDoc] = []
        with httpx.Client(timeout=45.0, follow_redirects=True, headers=_BROWSER_HEADERS) as client:
            if discover and account and len(urls) < max_articles:
                try:
                    found = _discover_via_sogou(client, account, limit=max_articles)
                    for item in found:
                        if item["url"] not in urls:
                            urls.append(item["url"])
                except Exception as exc:  # noqa: BLE001
                    docs.append(
                        FetchedDoc(
                            connector=self.name,
                            title=f"WeChat discover failed: {account}",
                            raw_text="",
                            status="failed",
                            error=str(exc),
                            metadata={"account": account},
                        )
                    )

            urls = _uniq(urls)[:max_articles]
            if not urls:
                docs.append(
                    FetchedDoc(
                        connector=self.name,
                        title=f"No WeChat URLs for: {account or '(empty)'}",
                        raw_text="",
                        status="failed",
                        error=(
                            "Provide connectors.wechat.urls, or an account name for Sogou discovery. "
                            "Official WeChat has no public list API."
                        ),
                        metadata={"account": account},
                    )
                )
                return docs

            for url in urls:
                doc = None
                last_err: str | None = None
                for attempt in range(3):
                    try:
                        doc = _fetch_article(client, url, expected_account=account or None)
                        if doc.status != "failed" or "captcha" not in (doc.error or "").lower() and "环境" not in (
                            doc.error or ""
                        ):
                            break
                        last_err = doc.error
                        time.sleep(1.2 * (attempt + 1))
                    except Exception as exc:  # noqa: BLE001
                        last_err = str(exc)
                        doc = None
                        time.sleep(1.2 * (attempt + 1))
                if doc is None:
                    docs.append(
                        FetchedDoc(
                            connector=self.name,
                            title=f"Fetch failed: {url}",
                            raw_text="",
                            url=url,
                            status="failed",
                            error=last_err or "unknown error",
                            metadata={"account": account},
                        )
                    )
                elif self.passes_filters(doc, scope):
                    docs.append(doc)
                time.sleep(0.6)
        return docs


def _fetch_article(
    client: httpx.Client,
    url: str,
    expected_account: str | None = None,
) -> FetchedDoc:
    if not _is_weixin_url(url) and not _is_http_url(url):
        return FetchedDoc(
            connector="wechat",
            title=f"Invalid URL: {url}",
            raw_text="",
            url=url,
            status="failed",
            error="Only http/https WeChat article URLs are allowed",
        )

    headers = dict(_BROWSER_HEADERS)
    if "weixin.sogou.com" in url:
        headers["Referer"] = "https://weixin.sogou.com/"
    elif "mp.weixin.qq.com" in url:
        headers["Referer"] = "https://weixin.sogou.com/"

    resp = client.get(url, headers=headers)
    resp.raise_for_status()
    html = resp.text
    final_url = str(resp.url)

    # Sogou jump page: assemble real mp.weixin URL from JS fragments
    if "weixin.sogou.com" in final_url or "url += '" in html[:2000]:
        assembled = _assemble_sogou_url(html)
        if assembled:
            resp = client.get(assembled, headers={**headers, "Referer": "https://weixin.sogou.com/"})
            resp.raise_for_status()
            html = resp.text
            final_url = str(resp.url)

    if _looks_like_captcha(html):
        return FetchedDoc(
            connector="wechat",
            title=f"WeChat blocked: {url}",
            raw_text="",
            url=final_url,
            status="failed",
            error="WeChat returned environment verification / captcha page",
            metadata={"requested_url": url},
        )

    title, authors, published_at, text, media, canonical = _extract_weixin(html, final_url)
    if expected_account and authors and authors != expected_account:
        # Still return content but mark mismatch for debugging
        meta_extra = {"account_mismatch": True, "expected_account": expected_account}
    else:
        meta_extra = {}

    if not text or len(text) < 40:
        return FetchedDoc(
            connector="wechat",
            title=title or f"Empty article: {url}",
            raw_text=text or "",
            url=canonical or final_url,
            authors=authors,
            published_at=published_at,
            status="failed",
            error="Could not extract js_content (page may be deleted or blocked)",
            metadata={"requested_url": url, **meta_extra},
        )

    return FetchedDoc(
        connector="wechat",
        title=title or (canonical or final_url),
        raw_text=f"{title}\n\n{text}".strip() if title else text,
        url=canonical or final_url,
        authors=authors,
        published_at=published_at,
        media=media,
        metadata={"requested_url": url, "biz": _extract_biz(html), **meta_extra},
    )


def _discover_via_sogou(client: httpx.Client, account: str, limit: int = 5) -> list[dict[str, str]]:
    """Discover recent articles mentioning the account via Sogou article search."""
    headers = {**_BROWSER_HEADERS, "Referer": "https://weixin.sogou.com/"}
    resp = client.get(
        "https://weixin.sogou.com/weixin",
        params={"type": 2, "query": account, "ie": "utf8"},
        headers=headers,
    )
    resp.raise_for_status()
    html = resp.text
    if _looks_like_captcha(html) or len(html) < 2000:
        raise RuntimeError("Sogou WeChat search blocked or returned empty results")

    items = re.findall(
        r'(?is)<h3[^>]*>\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html,
    )
    found: list[dict[str, str]] = []
    for href, title_html in items:
        if len(found) >= limit:
            break
        title = _clean_text(title_html)
        jump = urljoin("https://weixin.sogou.com", unescape(href))
        try:
            jump_resp = client.get(jump, headers=headers)
            wx_url = _assemble_sogou_url(jump_resp.text)
            if not wx_url:
                continue
            art = client.get(wx_url, headers={**headers, "Referer": "https://weixin.sogou.com/"})
            nick = _extract_nickname(art.text)
            if nick and nick != account:
                continue
            og = _extract_og_url(art.text) or str(art.url)
            found.append({"title": _extract_title(art.text) or title, "url": og})
            time.sleep(0.5)
        except Exception:  # noqa: BLE001
            continue
    if not found:
        raise RuntimeError(
            f"Sogou returned {len(items)} results but none matched account '{account}'"
        )
    return found


def _extract_weixin(
    html: str, base_url: str
) -> tuple[str, str | None, str | None, str, list[MediaAsset], str | None]:
    title = _extract_title(html)
    authors = _extract_nickname(html) or None
    published = None
    pub_m = re.search(
        r'(?is)<em[^>]+id=["\']publish_time["\'][^>]*>(.*?)</em>'
        r'|id=["\']publish_time["\'][^>]*>(.*?)<',
        html,
    )
    if pub_m:
        published = _clean_text(pub_m.group(1) or pub_m.group(2) or "") or None

    content_m = re.search(
        r'(?is)<div[^>]+id=["\']js_content["\'][^>]*>(.*)</div>\s*<script',
        html,
    )
    if not content_m:
        content_m = re.search(
            r'(?is)<div[^>]+id=["\']js_content["\'][^>]*>(.*?)</div>',
            html,
        )
    body_html = content_m.group(1) if content_m else ""

    media: list[MediaAsset] = []
    for m in re.finditer(
        r'(?is)<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']',
        body_html,
    ):
        src = urljoin(base_url, m.group(1).strip())
        if _is_http_url(src):
            media.append(MediaAsset(url=src, kind="image", filename_hint=_name_from_url(src)))
    seen: set[str] = set()
    uniq: list[MediaAsset] = []
    for asset in media:
        if asset.url in seen:
            continue
        seen.add(asset.url)
        uniq.append(asset)

    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", body_html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    canonical = _extract_og_url(html)
    # Prefer a stable /s/<id> form only when it matches this page's title context.
    # Blindly taking the first /s/ link in HTML often picks a related article.
    if base_url and re.search(r"mp\.weixin\.qq\.com/s/[A-Za-z0-9_\-]+", base_url):
        canonical = base_url.split("#", 1)[0]
    elif canonical and "signature=" not in canonical and "/s/" in canonical:
        pass
    else:
        # Keep signed og:url / final URL rather than guessing a wrong short link
        canonical = canonical or base_url

    return title, authors, published, text[:50000], uniq[:40], canonical


def _extract_title(html: str) -> str:
    m = re.search(r'(?is)<h1[^>]*id=["\']activity-name["\'][^>]*>(.*?)</h1>', html)
    if m:
        return _clean_text(m.group(1))
    m = re.search(r'(?is)<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html)
    if m:
        return _clean_text(m.group(1))
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    return _clean_text(m.group(1)) if m else ""


def _extract_nickname(html: str) -> str:
    m = re.search(r'(?is)<a[^>]+id=["\']js_name["\'][^>]*>(.*?)</a>', html)
    return _clean_text(m.group(1)) if m else ""


def _extract_og_url(html: str) -> str | None:
    m = re.search(
        r'(?is)<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
        html,
    )
    if not m:
        m = re.search(
            r'(?is)<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:url["\']',
            html,
        )
    return unescape(m.group(1)) if m else None


def _extract_biz(html: str) -> str | None:
    m = re.search(r"__biz=([A-Za-z0-9=]+)|biz\s*=\s*[\"']([A-Za-z0-9=]+)[\"']", html)
    if not m:
        return None
    return m.group(1) or m.group(2)


def _assemble_sogou_url(html: str) -> str | None:
    parts = re.findall(r"url\s*\+=\s*'([^']*)'", html)
    if not parts:
        return None
    return "".join(parts)


def _looks_like_captcha(html: str) -> bool:
    markers = ("环境异常", "完成验证后即可继续访问", "antispider", "验证码", "wappoc_appmsgcaptcha")
    return any(m in html for m in markers)


def _clean_text(value: str) -> str:
    value = unescape(re.sub(r"(?s)<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def _is_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:  # noqa: BLE001
        return False


def _is_weixin_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return "mp.weixin.qq.com" in host or "weixin.sogou.com" in host
    except Exception:  # noqa: BLE001
        return False


def _name_from_url(url: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] or "asset"
    return re.sub(r"[^\w.\-]+", "_", name)[:80]


def _uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
