"""Thinking Vault — Notion → Obsidian unidirectional sync package.

Phase 2: canonical model + normalizer + markdown serialization.
Adapter / writer / sync land in later phases.
"""

from .markdown import render_thinking_markdown
from .model import (
    BODY_SECTION_FIELDS,
    ConnectionRef,
    ThinkingObject,
    thinking_content_hash,
)
from .normalizer import normalize_thinking_properties

__all__ = [
    "BODY_SECTION_FIELDS",
    "ConnectionRef",
    "ThinkingObject",
    "normalize_thinking_properties",
    "render_thinking_markdown",
    "thinking_content_hash",
]
