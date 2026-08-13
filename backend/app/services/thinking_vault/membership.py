"""Folder membership index for Thinking Vault sync.

Rules:
- Type=folder pages list members in Related Information.
- A thinking page may belong to at most one folder.
- Conflicts leave the member at Thinking/ root and emit a warning.
- Nested folders: a folder listed inside another folder's Related Information
  is placed under that parent path.
- book/article pages are not written in this slim runtime and are not placed
  under folder directories.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import ThinkingObject
from .writer import natural_stem


@dataclass
class FolderMembership:
    """Resolved folder directories and thinking-member placement."""

    # folder source_id → vault-relative directory (e.g. Thinking/Neurology)
    folder_dirs: dict[str, str] = field(default_factory=dict)
    # thinking source_id → vault-relative parent dir under Thinking/
    thinking_dirs: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def build_folder_membership(
    objects: list[ThinkingObject],
    *,
    thinking_root: str = "Thinking",
) -> FolderMembership:
    """Build folder directory map and single-folder thinking placement."""
    result = FolderMembership()
    by_id = {o.source_id: o for o in objects if o.source_id}
    folders = [o for o in objects if o.is_folder()]
    if not folders:
        return result

    # child_folder_id → parent_folder_id (first claim wins for nesting)
    parent_of: dict[str, str] = {}
    # member_id → [folder_ids] for non-folder members (thinking placement)
    claims: dict[str, list[str]] = {}

    for folder in folders:
        for conn in folder.connections:
            mid = (conn.source_id or "").strip()
            if not mid or mid == folder.source_id:
                continue
            member = by_id.get(mid)
            if member is not None and member.is_folder():
                if mid not in parent_of:
                    parent_of[mid] = folder.source_id
                elif parent_of[mid] != folder.source_id:
                    result.warnings.append(
                        f"folder {mid} claimed by multiple parent folders; "
                        f"keeping parent {parent_of[mid]}"
                    )
                continue
            claims.setdefault(mid, []).append(folder.source_id)

    def resolve_folder_dir(fid: str) -> str:
        parts: list[str] = []
        seen: set[str] = set()
        cur: str | None = fid
        while cur:
            if cur in seen:
                result.warnings.append(f"folder cycle detected at {cur}; truncating path")
                break
            seen.add(cur)
            obj = by_id.get(cur)
            stem = natural_stem(obj.title if obj else cur)
            parts.append(stem)
            cur = parent_of.get(cur)
        parts.reverse()
        return "/".join([thinking_root, *parts])

    for folder in folders:
        result.folder_dirs[folder.source_id] = resolve_folder_dir(folder.source_id)

    for mid, folder_list in claims.items():
        unique = list(dict.fromkeys(folder_list))
        member = by_id.get(mid)
        if member is not None and not member.is_thinking():
            continue
        if len(unique) == 1:
            result.thinking_dirs[mid] = result.folder_dirs[unique[0]]
        elif len(unique) > 1:
            result.warnings.append(
                f"thinking page {mid} claimed by multiple folders {unique}; "
                f"leaving at {thinking_root}/"
            )

    return result
