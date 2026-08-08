"""Deprecated Obsidian entrypoints — Constitution V1 uses workspace.py.

Bulk Resource export is intentionally a no-op. Only promoted notes sync.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..schemas import ExportResult
from . import knowledge as knowledge_svc
from . import workspace as workspace_svc

# Re-exports for digest and older imports
write_report_note = workspace_svc.write_report_note
ensure_vault_scaffold = workspace_svc.ensure_scaffold
folder_for_kind = workspace_svc.folder_for_role
render_knowledge_note = workspace_svc.render_workspace_note


def export_knowledge_objects(
    db: Session,
    notebook: object,
    *,
    vault_path: str | None = None,
    ko_ids: list[str] | None = None,
    source_ids: list[str] | None = None,
) -> ExportResult:
    """Constitution: sync only promoted workspace notes — never Resource dumps."""
    vault = vault_path or getattr(notebook, "vault_path", None) or ""
    if not vault:
        raise ValueError("vault_path is required")
    notebook_id = getattr(notebook, "id", None)

    if ko_ids:
        written = 0
        last = ""
        for kid in ko_ids:
            ko = knowledge_svc.get_by_id(db, kid)
            if not ko or ko.workspace_role not in knowledge_svc.WORKSPACE_NOTE_ROLES:
                continue
            if ko.workspace_role == "report":
                continue
            path = workspace_svc.sync_note(db, ko, vault_path=vault)
            if path:
                written += 1
                last = str(path)
        return ExportResult(path=vault, brief_path=last or vault, sources_written=written)

    # source_ids: Resources are NOT synced (Constitution)
    if source_ids:
        return ExportResult(path=vault, brief_path=vault, sources_written=0)

    return workspace_svc.sync_workspace_notes(
        db, vault_path=vault, notebook_id=notebook_id
    )


def export_raw_to_obsidian(
    db: Session,
    notebook: object,
    docs: list | None = None,  # noqa: ARG001
    vault_path: str | None = None,
    download_media: bool = True,  # noqa: ARG001
) -> ExportResult:
    """No-op for capture dumps. Scaffold only; Resources stay in the Knowledge Database."""
    vault = vault_path or getattr(notebook, "vault_path", None) or ""
    if not vault:
        raise ValueError("vault_path is required")
    from pathlib import Path

    from ..utils import workspace_config_dict

    root = Path(vault).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    cfg = workspace_config_dict()
    if cfg.get("scaffold_folders", True):
        workspace_svc.ensure_scaffold(root, cfg)
    if hasattr(notebook, "vault_path"):
        notebook.vault_path = str(root)
        db.commit()
    return ExportResult(path=str(root), brief_path=str(root), sources_written=0)


def export_notebook_sources(
    db: Session,
    notebook,
    vault_path: str | None = None,
    download_media: bool = True,  # noqa: ARG001
) -> ExportResult:
    vault = vault_path or getattr(notebook, "vault_path", None) or ""
    if not vault:
        raise ValueError("vault_path is required")
    return workspace_svc.sync_workspace_notes(
        db, vault_path=vault, notebook_id=getattr(notebook, "id", None)
    )


def export_notebook(db: Session, notebook, vault_path: str | None = None) -> ExportResult:
    return export_notebook_sources(db, notebook, vault_path=vault_path)


def write_knowledge_note(db: Session, vault, ko, tpl=None):  # noqa: ARG001
    return workspace_svc.sync_note(db, ko, vault_path=str(vault))


def write_analysis_note(*_args, **_kwargs) -> str:
    return ""
