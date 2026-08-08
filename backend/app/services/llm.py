"""Thin LLM client (OpenAI-compatible + Anthropic) via httpx."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..config import get_settings


class LLMError(RuntimeError):
    pass


def is_configured() -> bool:
    settings = get_settings()
    provider = (settings.llm_provider or "openai").lower().strip()
    if provider == "anthropic":
        return bool(settings.anthropic_api_key)
    return bool(settings.openai_api_key)


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    json_mode: bool = False,
) -> str:
    settings = get_settings()
    provider = (settings.llm_provider or "openai").lower().strip()
    if provider == "anthropic":
        return _anthropic_chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    return _openai_chat(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )


def chat_json(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    text = chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=True)
    return _parse_json_object(text)


def _openai_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise LLMError("OPENAI_API_KEY is not configured")
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=90.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise LLMError(f"OpenAI error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected OpenAI response: {data!r}") from exc


def _anthropic_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
) -> str:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise LLMError("ANTHROPIC_API_KEY is not configured")
    system = ""
    converted: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role") or "user"
        content = m.get("content") or ""
        if role == "system":
            system = (system + "\n" + content).strip() if system else content
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        converted.append({"role": role, "content": content})
    if not converted:
        converted = [{"role": "user", "content": "Hello"}]
    payload: dict[str, Any] = {
        "model": settings.anthropic_model,
        "messages": converted,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if system:
        payload["system"] = system
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=90.0) as client:
        resp = client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
        )
        if resp.status_code >= 400:
            raise LLMError(f"Anthropic error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
    parts = data.get("content") or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
    if not texts:
        raise LLMError(f"Unexpected Anthropic response: {data!r}")
    return "\n".join(texts)


def _parse_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        obj = json.loads(m.group(0))
        if isinstance(obj, dict):
            return obj
    raise LLMError(f"Could not parse JSON from model output: {text[:400]}")
