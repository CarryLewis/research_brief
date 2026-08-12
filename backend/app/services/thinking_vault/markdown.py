"""Serialize Canonical Thinking Objects to Obsidian Markdown."""

from __future__ import annotations

from .model import ThinkingObject


def _yaml_scalar(value: str) -> str:
    """Minimal YAML scalar quoting for frontmatter."""
    text = value or ""
    if text == "":
        return '""'
    needs_quote = any(ch in text for ch in (":", "#", "{", "}", "[", "]", ",", "&", "*", "!", "|", ">", "%", "@", "`"))
    needs_quote = needs_quote or text.strip() != text or text.lower() in {"true", "false", "null", "yes", "no"}
    if needs_quote or "\n" in text:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def render_thinking_markdown(obj: ThinkingObject) -> str:
    """Render full note: frontmatter + H1 + non-empty sections."""
    lines = [
        "---",
        f"source: {_yaml_scalar(obj.source)}",
        f"source_id: {_yaml_scalar(obj.source_id)}",
    ]
    if obj.created_at:
        lines.append(f"created: {_yaml_scalar(obj.created_at)}")
    if obj.updated_at:
        lines.append(f"updated: {_yaml_scalar(obj.updated_at)}")
    lines.extend(["---", "", f"# {obj.title.strip()}", ""])

    for heading, body in obj.non_empty_sections():
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(body)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
