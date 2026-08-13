"""Convert Notion block children into Markdown for Thinking Vault page body."""

from __future__ import annotations

from typing import Any

from .normalizer import rich_text_to_plain


def blocks_to_markdown(blocks: list[dict[str, Any]] | None) -> str:
    """Render a flat/nested Notion block list to Markdown (best-effort)."""
    if not blocks:
        return ""
    lines: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        rendered = _render_block(block, depth=0)
        if rendered:
            lines.append(rendered)
    text = "\n\n".join(part for part in lines if part.strip())
    return text.strip()


def _block_rich_text(block: dict[str, Any], block_type: str) -> str:
    payload = block.get(block_type) or {}
    if not isinstance(payload, dict):
        return ""
    return rich_text_to_plain(payload.get("rich_text"))


def _render_block(block: dict[str, Any], *, depth: int) -> str:
    btype = str(block.get("type") or "")
    indent = "  " * depth
    text = _block_rich_text(block, btype) if btype else ""

    if btype == "paragraph":
        core = text
    elif btype == "heading_1":
        core = f"# {text}" if text else ""
    elif btype == "heading_2":
        core = f"## {text}" if text else ""
    elif btype == "heading_3":
        core = f"### {text}" if text else ""
    elif btype == "bulleted_list_item":
        core = f"{indent}- {text}" if text else f"{indent}-"
    elif btype == "numbered_list_item":
        core = f"{indent}1. {text}" if text else f"{indent}1."
    elif btype == "to_do":
        checked = bool((block.get("to_do") or {}).get("checked"))
        mark = "x" if checked else " "
        core = f"{indent}- [{mark}] {text}".rstrip()
    elif btype == "quote":
        quoted = "\n".join(f"> {line}" for line in (text or "").splitlines() or [""])
        core = quoted
    elif btype == "code":
        lang = str((block.get("code") or {}).get("language") or "").strip()
        core = f"```{lang}\n{text}\n```"
    elif btype == "divider":
        core = "---"
    elif btype in {"callout", "toggle"}:
        core = text
    elif btype == "image":
        image = block.get("image") or {}
        url = ""
        if image.get("type") == "external":
            url = str((image.get("external") or {}).get("url") or "")
        elif image.get("type") == "file":
            url = str((image.get("file") or {}).get("url") or "")
        caption = rich_text_to_plain(image.get("caption"))
        alt = caption or "image"
        core = f"![{alt}]({url})" if url else caption
    else:
        # Unsupported block types: keep plain text if any
        core = text

    children = block.get("_children") or []
    if children:
        child_md = []
        for child in children:
            part = _render_block(child, depth=depth + (1 if btype.endswith("_list_item") else 0))
            if part:
                child_md.append(part)
        if child_md:
            joined = "\n\n".join(child_md)
            core = f"{core}\n\n{joined}" if core else joined

    return (core or "").strip()
