"""Research Workspace (Obsidian) projection — thinking-first Constitution.

Only Concept / Project / Reflection / Book / Report notes are synced.
Resources stay in the Knowledge Database.

Reflections are human-owned freeform notes. Concept/Project/Book use a slim
machine skeleton with a preserved ## Notes section for human writing.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..db import KnowledgeObject, Reflection
from ..schemas import ExportResult
from ..utils import loads, workspace_config_dict
from . import knowledge as knowledge_svc


def ensure_scaffold(vault: Path, cfg: dict | None = None) -> None:
    cfg = cfg or workspace_config_dict()
    folders = cfg.get("folders") or {}
    for rel in folders.values():
        if isinstance(rel, str) and rel:
            (vault / rel).mkdir(parents=True, exist_ok=True)
    (vault / "90_Meta").mkdir(parents=True, exist_ok=True)


def folder_for_role(role: str, cfg: dict | None = None) -> str:
    cfg = cfg or workspace_config_dict()
    role_folders = cfg.get("role_folders") or {}
    folders = cfg.get("folders") or {}
    if role == "report":
        return folders.get("reports") or "Reports"
    return role_folders.get(role) or folders.get(role + "s") or role.capitalize() + "s"


def thinking_cfg(cfg: dict | None = None) -> dict:
    cfg = cfg or workspace_config_dict()
    raw = cfg.get("thinking") or {}
    return {
        "reflection_freeform": bool(raw.get("reflection_freeform", True)),
        "preserve_existing_reflection_files": bool(
            raw.get("preserve_existing_reflection_files", True)
        ),
        "preserve_human_notes_on_sync": bool(raw.get("preserve_human_notes_on_sync", True)),
    }


def sync_note(
    db: Session,
    ko: KnowledgeObject,
    *,
    vault_path: str,
    force: bool = False,
) -> Path | None:
    """Write or update one workspace note. No-op for resources.

    Reflections: create when missing; skip overwrite when file exists unless force=True
    (API create/update uses force so body_md can land in the vault).
    """
    role = (ko.workspace_role or "resource").lower()
    if role not in knowledge_svc.WORKSPACE_NOTE_ROLES:
        return None
    if role == "report":
        # Reports use write_report_note with period paths
        return None

    vault = Path(vault_path).expanduser()
    cfg = workspace_config_dict()
    tcfg = thinking_cfg(cfg)
    if cfg.get("scaffold_folders", True):
        ensure_scaffold(vault, cfg)

    folder = folder_for_role(role, cfg)
    out_dir = vault / folder
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = _natural_stem(ko.title)
    note_path = out_dir / f"{stem}.md"
    if note_path.exists() and ko.vault_path:
        existing = vault / ko.vault_path
        if existing.is_file() and existing.resolve() != note_path.resolve():
            # Title collision with a different note — disambiguate by words, not ids
            note_path = out_dir / f"{stem} ({role}).md"

    # Prefer known vault_path if it still exists (stable path after renames)
    if ko.vault_path:
        known = vault / ko.vault_path
        if known.is_file():
            note_path = known

    if (
        role == "reflection"
        and tcfg["preserve_existing_reflection_files"]
        and note_path.is_file()
        and not force
    ):
        ko.vault_path = str(note_path.relative_to(vault))
        db.commit()
        return note_path

    human_notes = ""
    if (
        role != "reflection"
        and tcfg["preserve_human_notes_on_sync"]
        and note_path.is_file()
    ):
        human_notes = extract_human_notes(note_path.read_text(encoding="utf-8"))

    body = render_workspace_note(db, ko, cfg, human_notes=human_notes)
    note_path.write_text(body, encoding="utf-8")
    ko.vault_path = str(note_path.relative_to(vault))
    db.commit()
    return note_path


def sync_workspace_notes(
    db: Session,
    *,
    vault_path: str,
    notebook_id: str | None = None,
) -> ExportResult:
    """Sync all promoted workspace notes (not Resources)."""
    vault = Path(vault_path).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    cfg = workspace_config_dict()
    if cfg.get("scaffold_folders", True):
        ensure_scaffold(vault, cfg)

    kos = knowledge_svc.list_workspace_notes(db, notebook_id)
    written = 0
    last: Path | None = None
    for ko in kos:
        if ko.workspace_role == "report":
            continue
        path = sync_note(db, ko, vault_path=str(vault))
        if path:
            written += 1
            last = path
    return ExportResult(
        path=str(vault),
        brief_path=str(last) if last else str(vault),
        sources_written=written,
    )


def render_workspace_note(
    db: Session,
    ko: KnowledgeObject,
    cfg: dict | None = None,
    *,
    human_notes: str = "",
) -> str:
    cfg = cfg or workspace_config_dict()
    tcfg = thinking_cfg(cfg)
    role = (ko.workspace_role or ko.kind or "resource").lower()

    if role == "reflection" and tcfg["reflection_freeform"]:
        return _render_freeform_reflection(db, ko)

    return _render_structured_note(db, ko, cfg, human_notes=human_notes)


def _render_freeform_reflection(db: Session, ko: KnowledgeObject) -> str:
    """Minimal frontmatter + title + body_md (no six-section skeleton)."""
    ref = db.query(Reflection).filter(Reflection.id == ko.id).first()
    body = (ref.body_md if ref else "") or ""
    # Prefer dedicated body; fall back to summary for legacy rows
    if not body.strip():
        body = (ko.summary or "").strip()
    date_str = _note_date(ko)
    graph = "true" if ko.graph_eligible else "false"
    lines = [
        "---",
        f'title: "{_yaml_escape(ko.title)}"',
        "type: reflection",
        f"date: {date_str}",
        f"graph: {graph}",
        "---",
        "",
        f"# {ko.title}",
        "",
    ]
    if body.strip():
        # Avoid duplicating the H1 if body already starts with it
        stripped = body.strip()
        h1 = f"# {ko.title}"
        if stripped.startswith(h1):
            rest = stripped[len(h1) :].lstrip("\n")
            if rest:
                lines.append(rest)
        else:
            lines.append(stripped)
        lines.append("")
    else:
        lines.append("")
    return "\n".join(lines)


def _render_structured_note(
    db: Session,
    ko: KnowledgeObject,
    cfg: dict,
    *,
    human_notes: str = "",
) -> str:
    """Slim template: Summary, Key Ideas, Connections, Notes, References (+ role extras)."""
    limits = cfg.get("limits") or {}
    max_ideas = int(limits.get("max_key_ideas") or 12)
    max_conn = int(limits.get("max_connections") or 8)

    role = (ko.workspace_role or ko.kind or "concept").lower()
    tags = knowledge_svc.normalize_filter_tags(loads(ko.tags_json, []) or [])
    key_ideas = loads(ko.key_points_json, []) or []
    connections = knowledge_svc.related_topic_names(db, ko, max_n=max_conn)
    date_str = _note_date(ko)
    summary = (ko.summary or "").strip()
    graph = "true" if ko.graph_eligible else "false"
    if role == "report":
        graph = "false"

    lines = [
        "---",
        f'title: "{_yaml_escape(ko.title)}"',
        f"type: {role}",
        f"date: {date_str}",
        "status: active",
        "tags:",
        *([f"  - {t}" for t in tags] if tags else ["  -"]),
        f"graph: {graph}",
        "---",
        "",
        f"# {ko.title}",
        "",
        "## Summary",
        "",
        summary or "",
        "",
        "## Key Ideas",
        "",
    ]
    if key_ideas:
        for p in key_ideas[:max_ideas]:
            lines.append(f"- {p}")
    else:
        lines.append("")
    lines.extend(["", "## Connections", ""])
    if connections:
        for name in connections:
            lines.append(f"[[{name}]]")
    else:
        lines.append("")

    if role == "book":
        lines.extend(
            [
                "",
                "## Reading Progress",
                "",
                "",
                "## Highlights",
                "",
                "",
            ]
        )
    if role == "project":
        lines.extend(
            [
                "",
                "## Objectives",
                "",
                "",
                "## Roadmap",
                "",
                "",
            ]
        )

    lines.extend(["", "## Notes", ""])
    if human_notes.strip():
        lines.append(human_notes.strip())
        lines.append("")
    else:
        lines.append("")

    lines.extend(["## References", ""])
    if ko.source_url:
        lines.append(f"- {ko.source_url}")
    else:
        lines.append("")
    lines.append("")
    return "\n".join(lines)


def extract_human_notes(markdown: str) -> str:
    """Pull ## Notes (preferred) or legacy ## My Reflection body from an existing note."""
    notes = _section_body(markdown, "Notes")
    if notes.strip():
        return notes.strip()
    legacy = _section_body(markdown, "My Reflection")
    return legacy.strip()


def _section_body(markdown: str, heading: str) -> str:
    """Return text under ## {heading} until the next ## heading or EOF."""
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(markdown or "")
    if not m:
        return ""
    return m.group(1)


def write_report_note(
    *,
    vault_path: str,
    period: str,
    content_md: str,
    period_end: datetime | None = None,
    subject: str = "",
) -> str:
    """Write a digest report. graph: false — reports do not pollute the idea graph."""
    vault = Path(vault_path).expanduser()
    cfg = workspace_config_dict()
    if cfg.get("scaffold_folders", True):
        ensure_scaffold(vault, cfg)

    folders = cfg.get("folders") or {}
    period = (period or "daily").lower()
    end = period_end or datetime.now(timezone.utc)
    if period == "weekly":
        rel_folder = folders.get("reports_weekly") or "Reports/Weekly"
        stem = _iso_week_stem(end)
    else:
        rel_folder = folders.get("reports_daily") or "Reports/Daily"
        stem = end.astimezone(timezone.utc).strftime("%Y-%m-%d")

    out_dir = vault / rel_folder
    out_dir.mkdir(parents=True, exist_ok=True)
    note_path = out_dir / f"{stem}.md"

    body = content_md.strip() if content_md.strip() else ""
    date_s = end.astimezone(timezone.utc).strftime("%Y-%m-%d")
    front = [
        "---",
        f'title: "{_yaml_escape(subject or stem)}"',
        "type: report",
        f"period: {period}",
        f"date: {date_s}",
        "status: active",
        "tags:",
        "  - review",
        "graph: false",
        "---",
        "",
    ]
    if body and not body.lstrip().startswith("#"):
        front.append(f"# {subject or stem}")
        front.append("")
    note = "\n".join(front) + (body + "\n" if body else "\n")
    note_path.write_text(note, encoding="utf-8")
    return str(note_path)


def archive_note(vault_path: str, relative_path: str) -> str | None:
    """Move a workspace note under Archive/. Returns new relative path."""
    vault = Path(vault_path).expanduser()
    src = vault / relative_path
    if not src.is_file():
        return None
    dest_dir = vault / "Archive"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        dest = dest_dir / f"{src.stem} archived{src.suffix}"
    shutil.move(str(src), str(dest))
    return str(dest.relative_to(vault))


def _natural_stem(title: str) -> str:
    """Human-readable filename: spaces kept as spaces where safe; strip junk."""
    cleaned = (title or "Untitled").strip()
    cleaned = cleaned.replace("/", "-").replace("\\", "-")
    for ch in ':*?"<>|':
        cleaned = cleaned.replace(ch, "")
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        cleaned = "Untitled"
    # Obsidian-friendly length
    return cleaned[:120]


def _note_date(ko: KnowledgeObject) -> str:
    if ko.published_at:
        return str(ko.published_at)[:10]
    if ko.created_at:
        dt = ko.created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _iso_week_stem(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
