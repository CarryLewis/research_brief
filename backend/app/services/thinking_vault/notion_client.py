"""Thin Notion API client (read-only for Thinking Vault V1)."""

from __future__ import annotations

import logging
from typing import Any, Iterator

import httpx

logger = logging.getLogger(__name__)

NOTION_VERSION = "2022-06-28"
NOTION_API_BASE = "https://api.notion.com/v1"


class NotionAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class NotionClient:
    """Minimal Notion REST client used by the Thinking Adapter."""

    def __init__(
        self,
        token: str,
        *,
        client: httpx.Client | None = None,
        timeout: float = 45.0,
    ) -> None:
        if not (token or "").strip():
            raise NotionAPIError("NOTION_TOKEN is empty")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=NOTION_API_BASE,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token.strip()}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> NotionClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("Notion request failed: %s %s — %s", method, path, exc)
            raise NotionAPIError(f"Notion network failure: {exc}") from exc
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                body = resp.text
            logger.error(
                "Notion API error %s %s → %s: %s",
                method,
                path,
                resp.status_code,
                body,
            )
            raise NotionAPIError(
                f"Notion API {resp.status_code} for {method} {path}",
                status_code=resp.status_code,
                body=body,
            )
        if not resp.content:
            return {}
        return resp.json()

    def query_database(
        self,
        database_id: str,
        *,
        start_cursor: str | None = None,
        page_size: int = 100,
        filter_obj: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"page_size": page_size}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        if filter_obj:
            payload["filter"] = filter_obj
        db_id = _normalize_notion_id(database_id)
        return self._request("POST", f"/databases/{db_id}/query", json=payload)

    def iter_database_pages(
        self,
        database_id: str,
        *,
        page_size: int = 100,
        filter_obj: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        cursor: str | None = None
        while True:
            data = self.query_database(
                database_id,
                start_cursor=cursor,
                page_size=page_size,
                filter_obj=filter_obj,
            )
            for row in data.get("results") or []:
                yield row
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        return self._request("GET", f"/pages/{_normalize_notion_id(page_id)}")


def _normalize_notion_id(value: str) -> str:
    raw = (value or "").strip().replace("-", "")
    if len(raw) == 32 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"
    return (value or "").strip()
