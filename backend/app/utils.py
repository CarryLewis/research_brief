from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

import yaml

from .config import CONFIGS_DIR


def new_id(prefix: str = "") -> str:
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}_{uid}" if prefix else uid


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def default_scope_dict() -> dict[str, Any]:
    return load_yaml(CONFIGS_DIR / "default_scope.yaml")


def default_analysis_dict() -> dict[str, Any]:
    return load_yaml(CONFIGS_DIR / "default_analysis.yaml")


def obsidian_template_dict() -> dict[str, Any]:
    """Load workspace config (Constitution). Falls back to legacy filename."""
    return workspace_config_dict()


def workspace_config_dict() -> dict[str, Any]:
    primary = CONFIGS_DIR / "workspace.yaml"
    if primary.is_file():
        return load_yaml(primary)
    legacy = CONFIGS_DIR / "obsidian_template.yaml"
    if legacy.is_file():
        return load_yaml(legacy)
    return {}


def lifecycle_config_dict() -> dict[str, Any]:
    path = CONFIGS_DIR / "lifecycle.yaml"
    if path.is_file():
        return load_yaml(path)
    return {}


def graph_config_dict() -> dict[str, Any]:
    path = CONFIGS_DIR / "graph.yaml"
    if path.is_file():
        return load_yaml(path)
    return {}


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def loads(s: str, default: Any = None) -> Any:
    if not s:
        return default
    return json.loads(s)


def sanitize_filename(name: str, max_len: int = 80) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "", name)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = cleaned.strip("._") or "untitled"
    return cleaned[:max_len]


def tokenize(text: str) -> list[str]:
    text = text.lower()
    # Keep CJK chars as unigrams and latin words
    tokens: list[str] = []
    for match in re.finditer(r"[\u4e00-\u9fff]|[a-z0-9]{2,}", text):
        tokens.append(match.group(0))
    return tokens


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def excerpt(text: str, limit: int = 240) -> str:
    t = re.sub(r"\s+", " ", text.strip())
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"
