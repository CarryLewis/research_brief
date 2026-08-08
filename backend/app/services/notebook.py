from __future__ import annotations

from sqlalchemy.orm import Session

from ..db import Notebook, SourceDoc, utcnow
from ..schemas import (
    AnalysisSpec,
    NotebookCreate,
    NotebookOut,
    NotebookUpdate,
    ScopeSpec,
)
from ..utils import (
    default_analysis_dict,
    default_scope_dict,
    dumps,
    loads,
    new_id,
)


def _merge_scope(data: dict | None) -> ScopeSpec:
    base = default_scope_dict()
    if data:
        base = _deep_merge(base, data)
    return ScopeSpec.model_validate(base)


def _merge_analysis(data: dict | None) -> AnalysisSpec:
    base = default_analysis_dict()
    if data:
        base = _deep_merge(base, data)
    return AnalysisSpec.model_validate(base)


def _deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def notebook_to_out(db: Session, nb: Notebook) -> NotebookOut:
    count = db.query(SourceDoc).filter(SourceDoc.notebook_id == nb.id).count()
    return NotebookOut(
        id=nb.id,
        title=nb.title,
        topic=nb.topic,
        scope=ScopeSpec.model_validate(loads(nb.scope_json, {})),
        analysis=AnalysisSpec.model_validate(loads(nb.analysis_json, {})),
        vault_path=nb.vault_path,
        created_at=nb.created_at,
        updated_at=nb.updated_at,
        source_count=count,
    )


def create_notebook(db: Session, payload: NotebookCreate) -> NotebookOut:
    scope = payload.scope or _merge_scope({"topic": payload.topic})
    if payload.topic and not scope.topic:
        scope.topic = payload.topic
    analysis = payload.analysis or _merge_analysis(None)
    nb = Notebook(
        id=new_id("nb"),
        title=payload.title,
        topic=payload.topic or scope.topic or payload.title,
        scope_json=dumps(scope.model_dump(by_alias=True)),
        analysis_json=dumps(analysis.model_dump()),
        vault_path=payload.vault_path,
    )
    db.add(nb)
    db.commit()
    db.refresh(nb)
    return notebook_to_out(db, nb)


def list_notebooks(db: Session) -> list[NotebookOut]:
    rows = db.query(Notebook).order_by(Notebook.updated_at.desc()).all()
    return [notebook_to_out(db, n) for n in rows]


def get_notebook(db: Session, notebook_id: str) -> Notebook | None:
    return db.get(Notebook, notebook_id)


def update_notebook(db: Session, nb: Notebook, payload: NotebookUpdate) -> NotebookOut:
    if payload.title is not None:
        nb.title = payload.title
    if payload.topic is not None:
        nb.topic = payload.topic
    if payload.scope is not None:
        nb.scope_json = dumps(payload.scope.model_dump(by_alias=True))
        if payload.scope.topic:
            nb.topic = payload.scope.topic
    if payload.analysis is not None:
        nb.analysis_json = dumps(payload.analysis.model_dump())
    if payload.vault_path is not None:
        nb.vault_path = payload.vault_path
    nb.updated_at = utcnow()
    db.commit()
    db.refresh(nb)
    return notebook_to_out(db, nb)


def delete_notebook(db: Session, nb: Notebook) -> None:
    db.delete(nb)
    db.commit()
