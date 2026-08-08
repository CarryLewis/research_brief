from __future__ import annotations

from typing import Any

from ..config import CONFIGS_DIR
from ..utils import load_yaml, new_id


def load_channel_catalog() -> list[dict[str, Any]]:
    data = load_yaml(CONFIGS_DIR / "channels.yaml")
    return list(data.get("channels") or [])


def list_channels_for_api() -> list[dict[str, Any]]:
    return load_channel_catalog()


def resolve_ingest_plan(
    scope: dict[str, Any],
    selected_channel_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build an effective scope for connectors from:
    - preset channel catalog selections
    - user custom channels
    - optional explicit connector override list
    """
    catalog = {c["id"]: c for c in load_channel_catalog()}
    custom = list(scope.get("custom_channels") or [])
    custom_by_id = {c.get("id"): c for c in custom if c.get("id")}

    selected = selected_channel_ids
    if selected is None:
        selected = list(scope.get("selected_channels") or [])

    extras_rss = ((scope.get("connectors") or {}).get("rss") or {}).get("feeds") or []
    extras_web = ((scope.get("connectors") or {}).get("web") or {}).get("urls") or []
    extras_wechat_cfg = ((scope.get("connectors") or {}).get("wechat") or {})
    extras_wechat = extras_wechat_cfg.get("urls") or []
    extras_wechat_account = (extras_wechat_cfg.get("account") or "").strip()
    has_extras = any(extras_rss) or any(extras_web) or any(extras_wechat) or bool(extras_wechat_account)

    if not selected:
        if has_extras:
            selected = []
        else:
            selected = [c["id"] for c in catalog.values() if c.get("enabled_by_default")]
            selected.extend([c["id"] for c in custom if c.get("enabled", True)])

    feed_urls: list[str] = []
    web_urls: list[str] = []
    wechat_urls: list[str] = []
    wechat_account = extras_wechat_account
    wechat_max: int | None = None
    connectors_needed: set[str] = set()

    for cid in selected:
        if cid in catalog:
            ch = catalog[cid]
            connector = ch.get("connector")
            if connector in {"pubmed", "email", "rss", "web", "wechat"}:
                connectors_needed.add(connector)
            if ch.get("feed_url"):
                feed_urls.append(ch["feed_url"])
                connectors_needed.add("rss")
            if connector == "wechat":
                account = (ch.get("account") or ch.get("name") or "").strip()
                if account and not wechat_account:
                    wechat_account = account
                for u in ch.get("urls") or []:
                    if u:
                        wechat_urls.append(u)
                if ch.get("max_articles"):
                    wechat_max = int(ch["max_articles"])
        elif cid in custom_by_id:
            ch = custom_by_id[cid]
            if not ch.get("enabled", True):
                continue
            kind = (ch.get("kind") or "rss").lower()
            url = (ch.get("url") or "").strip()
            if kind == "wechat":
                connectors_needed.add("wechat")
                if ch.get("name") and not wechat_account:
                    wechat_account = ch["name"]
                if url:
                    wechat_urls.append(url)
                continue
            if not url:
                continue
            if kind in {"web", "url"}:
                web_urls.append(url)
                connectors_needed.add("web")
            else:
                feed_urls.append(url)
                connectors_needed.add("rss")

    for u in extras_rss:
        if u:
            feed_urls.append(u)
            connectors_needed.add("rss")
    for u in extras_web:
        if u:
            web_urls.append(u)
            connectors_needed.add("web")
    for u in extras_wechat:
        if u:
            wechat_urls.append(u)
            connectors_needed.add("wechat")
    if extras_wechat_account and not wechat_account:
        wechat_account = extras_wechat_account
        connectors_needed.add("wechat")

    feed_urls = _uniq(feed_urls)
    web_urls = _uniq(web_urls)
    wechat_urls = _uniq(wechat_urls)

    effective = dict(scope)
    connectors = dict(effective.get("connectors") or {})
    rss = dict(connectors.get("rss") or {})
    web = dict(connectors.get("web") or {})
    wechat = dict(connectors.get("wechat") or {})
    rss["feeds"] = feed_urls
    web["urls"] = web_urls
    if wechat_account:
        wechat["account"] = wechat_account
    if wechat_urls:
        wechat["urls"] = wechat_urls
    if wechat_max is not None:
        wechat["max_articles"] = wechat_max
    connectors["rss"] = rss
    connectors["web"] = web
    connectors["wechat"] = wechat
    effective["connectors"] = connectors
    effective["source_types"] = sorted(connectors_needed) if connectors_needed else list(
        effective.get("source_types") or []
    )
    effective["_selected_channels"] = selected
    return effective


def make_custom_channel(
    name: str,
    url: str,
    kind: str = "rss",
    enabled: bool = True,
) -> dict[str, Any]:
    return {
        "id": new_id("ch"),
        "name": name or url,
        "kind": kind if kind in {"rss", "web", "url"} else "rss",
        "url": url,
        "enabled": enabled,
    }


def _uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
