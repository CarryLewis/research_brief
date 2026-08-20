from __future__ import annotations

import hashlib
import re


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def sanitize_filename(name: str, max_len: int = 80) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "", name)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = cleaned.strip("._") or "untitled"
    return cleaned[:max_len]
