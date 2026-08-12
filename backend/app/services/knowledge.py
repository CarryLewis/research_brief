"""Knowledge Object domain — Knowledge Database (not the Obsidian workspace)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db import ConceptSuggestion, KnowledgeObject, KoLink, SourceDoc, utcnow
from ..schemas import AnalysisOut
from ..utils import dumps, loads, new_id, sanitize_filename, workspace_config_dict
from . import content_lake as lake_svc
from . import lifecycle as life_svc

PRIMARY_KINDS = frozenset(
    {
        "article",
        "paper",
        "book",
        "news",
        "newsletter",
        "podcast",
        "video",
        "image",
        "audio",
        "meeting",
        "reflection",
        "project",
        "report",
        "concept",
        "other",
    }
)

# Roles that may sync into the Obsidian cognitive vault (V1.1)
# Legacy typed roles remap to Information / Thinking / Research folders.
WORKSPACE_NOTE_ROLES = frozenset(
    {
        "information",
        "thinking",
        "research",
        "concept",
        "project",
        "reflection",
        "insight",
        "book",
        "question",
        "report",
    }
)
# Promote accepts cognitive roles and legacy aliases
PROMOTE_ROLES = frozenset(
    {
        "information",
        "thinking",
        "research",
        "concept",
        "project",
        "reflection",
        "book",
        "insight",
    }
)

# Optional soft vocabulary only — empty config allowlist disables domain enforcement.
# Kept as a soft union for backward-compatible callers; not a required taxonomy.
FILTER_TAG_ALLOWLIST = frozenset(
    {
        "important",
        "todo",
        "review",
    }
)

# Folder / type / state tokens that must never become note tags (V1.1 Conflict D)
_COGNITIVE_FOLDER_TAG_REJECT = frozenset(
    {
        "information",
        "thinking",
        "research",
        "resource",
        "workspace",
        "pipeline",
        "database",
        "inbox",
        "archived",
        "concept",
        "project",
        "reflection",
        "insight",
        "report",
        "signal",
        "knowledge-object",
        "knowledge_object",
    }
)

CONNECTOR_KIND = {
    "pubmed": "paper",
    "email": "newsletter",
    "rss": "article",
    "web": "article",
    "wechat": "article",
    "manual": "article",
}

_LEGACY_TAG_REJECT = frozenset(
    {
        "raw-text",
        "raw-index",
        "analysis",
        "source",
        "captured",
        "ready",
        "partial",
        "failed",
        *PRIMARY_KINDS,  # type tags are not Obsidian filters
    }
)


def infer_kind(connector: str, metadata: dict | None = None) -> str:
    meta = metadata or {}
    explicit = (meta.get("kind") or meta.get("source_kind") or "").strip().lower()
    if explicit in PRIMARY_KINDS:
        return explicit
    if connector == "email" or meta.get("source_kind") == "email":
        return "newsletter"
    if meta.get("source_kind") == "article":
        return "article"
    return CONNECTOR_KIND.get((connector or "").lower(), "article")


def default_workspace_role(kind: str) -> str:
    """Capture defaults to resource. Only explicit workspace kinds map otherwise."""
    if kind in WORKSPACE_NOTE_ROLES:
        return kind
    return "resource"


def graph_eligible_for_role(role: str) -> int:
    """Cognitive objects may enter the graph; digests/reports do not."""
    role = (role or "").lower()
    if role in {"report", "archived", "resource", "signal"}:
        return 0
    if role in WORKSPACE_NOTE_ROLES:
        return 1
    return 0


def normalize_filter_tags(
    analysis_tags: list[str] | None = None,
    *,
    max_tags: int = 5,
) -> list[str]:
    """Optional light tags for notes — never a second taxonomy (Constitution V1.1).

    Rejects type/pipeline/folder/state tokens. If ``filter_tag_allowlist`` is empty,
    only strips rejected tokens (no domain allowlist enforcement).
    """
    cfg = workspace_config_dict()
    cfg_allow = cfg.get("filter_tag_allowlist")
    # Empty list in config = do not enforce domain allowlist
    if isinstance(cfg_allow, list) and len(cfg_allow) == 0:
        allow: set[str] | None = None
    else:
        allow = set(cfg_allow or []) | FILTER_TAG_ALLOWLIST
    max_tags = int((cfg.get("limits") or {}).get("max_filter_tags") or max_tags)
    out: list[str] = []
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in analysis_tags or []:
        tag = _normalize_tag_token(raw)
        if tag and tag not in seen:
            ordered.append(tag)
            seen.add(tag)
    candidates = ordered
    if allow is not None:
        candidates = [t for t in ordered if t in allow] + [
            t for t in ordered if t not in allow
        ]
    for tag in candidates:
        if tag in _LEGACY_TAG_REJECT or tag in _COGNITIVE_FOLDER_TAG_REJECT:
            continue
        if "/" in tag:  # reject namespaced implementation tags
            continue
        if tag not in out:
            out.append(tag)
        if len(out) >= max_tags:
            break
    return out


# Back-compat alias used by older callers/tests
def normalize_tags(
    kind: str,
    analysis_tags: list[str] | None = None,
    *,
    max_secondary: int = 5,
) -> list[str]:
    """DB-side tags: kind kept in metadata; filter tags from analysis."""
    filters = normalize_filter_tags(analysis_tags, max_tags=max_secondary)
    # Keep kind in DB tags for querying Resources; Obsidian projection strips type tags
    primary = kind if kind in PRIMARY_KINDS else "other"
    if primary not in filters:
        return [primary, *filters][: max_secondary + 1]
    return filters[: max_secondary + 1]


def _normalize_tag_token(raw: str) -> str:
    t = (raw or "").strip().lower()
    if not t:
        return ""
    for prefix in ("type/", "source/", "topic/", "status/", "tag/", "#"):
        if t.startswith(prefix):
            t = t[len(prefix) :]
    t = sanitize_filename(t).lower().replace("_", "-")
    t = t.strip("-")
    if not t or t in {"raw-text", "raw-index", "analysis", "source", "captured"}:
        return ""
    return t[:40]


def upsert_from_source(
    db: Session,
    source: SourceDoc,
    *,
    kind: str | None = None,
    store_lake: bool = True,
    store_media: bool = True,
    language: str = "",
) -> KnowledgeObject:
    """Create/update a Resource KO from capture. Never promotes to Obsidian."""
    meta = loads(source.metadata_json, {}) or {}
    resolved_kind = kind or infer_kind(source.connector, meta)

    existing = (
        db.query(KnowledgeObject)
        .filter(KnowledgeObject.source_doc_id == source.id)
        .first()
    )
    stage = life_svc.initial_stage_for_connector(source.connector)
    # Papers / kept resources write to Lake immediately; signals wait until kept
    will_store_lake = store_lake and stage != "signal"

    if existing:
        ko = existing
        ko.title = source.title
        # Do not demote an already-promoted note back to resource on re-ingest
        if ko.workspace_role in ("resource", "archived") or not ko.workspace_role:
            ko.kind = resolved_kind
            ko.workspace_role = "resource"
            ko.graph_eligible = 0
        ko.source_url = source.url
        ko.authors = source.authors
        ko.published_at = source.published_at
        ko.connector = source.connector
        ko.content_hash = source.content_hash
        ko.status = _map_status(source.status)
        if language:
            ko.language = language
        ko.metadata_json = dumps(meta)
    else:
        ko = KnowledgeObject(
            id=new_id("ko"),
            notebook_id=source.notebook_id,
            source_doc_id=source.id,
            kind=resolved_kind,
            title=source.title,
            summary="",
            key_points_json="[]",
            language=language or _guess_language(meta),
            reading_status="unread",
            importance="medium",
            status=_map_status(source.status),
            source_url=source.url,
            authors=source.authors,
            published_at=source.published_at,
            connector=source.connector,
            content_hash=source.content_hash,
            tags_json=dumps([resolved_kind]),
            entities_json="[]",
            metadata_json=dumps(meta),
            workspace_role="resource",
            graph_eligible=0,
            lifecycle_stage=stage,
            filter_status="pending" if stage == "signal" else "kept",
            lifecycle_updated_at=utcnow(),
        )
        db.add(ko)
        db.commit()
        db.refresh(ko)
        life_svc.record_event(
            db,
            ko,
            from_stage="",
            to_stage=stage,
            trigger="capture",
            actor="system",
            payload={"connector": source.connector, "kind": resolved_kind},
        )

    if will_store_lake and (source.raw_text or "").strip():
        ref = lake_svc.put_text(
            db,
            source.raw_text,
            role="original",
            ko_id=ko.id,
            filename=f"{sanitize_filename(source.title)}.txt",
        )
        ko.primary_content_uri = ref.uri
        if (ko.lifecycle_stage or "") == "signal":
            life_svc.keep_signal(db, ko)
            db.refresh(ko)

    if store_media:
        for m in meta.get("media") or []:
            if not isinstance(m, dict) or not m.get("url"):
                continue
            from ..connectors.base import MediaAsset

            lake_svc.store_media_asset(
                db,
                MediaAsset(
                    url=m["url"],
                    kind=m.get("kind") or "other",
                    filename_hint=m.get("filename_hint"),
                ),
                ko_id=ko.id,
            )

    tags = loads(ko.tags_json, []) or []
    if resolved_kind not in tags and ko.workspace_role == "resource":
        ko.tags_json = dumps(normalize_tags(resolved_kind, tags))

    db.commit()
    db.refresh(ko)
    return ko


def apply_analysis(db: Session, ko: KnowledgeObject, analysis: AnalysisOut) -> KnowledgeObject:
    ko.summary = (analysis.summary or "").strip()
    ko.key_points_json = dumps(list(analysis.key_points or []))
    ko.entities_json = dumps(list(analysis.entities or []))
    ko.tags_json = dumps(normalize_tags(ko.kind, analysis.tags))
    ko.status = "ready"
    # If this was a signal, persist original into Lake now that we keep it
    if not ko.primary_content_uri and ko.source_doc_id:
        src = db.query(SourceDoc).filter(SourceDoc.id == ko.source_doc_id).first()
        if src and (src.raw_text or "").strip():
            ref = lake_svc.put_text(
                db,
                src.raw_text,
                role="original",
                ko_id=ko.id,
                filename=f"{sanitize_filename(ko.title)}.txt",
            )
            ko.primary_content_uri = ref.uri
    # Record entity mentions for suggestions — do NOT create Obsidian concept files
    record_entity_mentions(db, analysis.entities or [], notebook_id=ko.notebook_id)
    db.commit()
    db.refresh(ko)
    # Lifecycle: resource/signal → knowledge_object
    life_svc.mark_analyzed(db, ko, confidence=0.6)
    db.refresh(ko)
    # Link entities to concept candidates via edges (resolved when concept exists)
    for ent in (analysis.entities or [])[:8]:
        name = (ent or "").strip()
        if not name:
            continue
        target = (
            db.query(KnowledgeObject)
            .filter(
                KnowledgeObject.notebook_id == ko.notebook_id,
                KnowledgeObject.kind == "concept",
                KnowledgeObject.title == name,
            )
            .first()
        )
        exists = (
            db.query(KoLink)
            .filter(
                KoLink.from_ko_id == ko.id,
                KoLink.link_type == "about",
                KoLink.to_name == name,
            )
            .first()
        )
        if exists:
            if target and not exists.to_ko_id:
                exists.to_ko_id = target.id
                exists.to_type = "concept"
                db.commit()
            continue
        life_svc.create_edge(
            db,
            from_ko_id=ko.id,
            to_ko_id=target.id if target else None,
            to_name=name,
            edge_type="about",
            from_type="ko",
            to_type="concept" if target else "ko",
            created_by="ai",
        )
    life_svc.evaluate_workspace(db, ko.notebook_id)
    db.refresh(ko)
    return ko


def record_entity_mentions(
    db: Session,
    entities: list[str],
    *,
    notebook_id: str | None = None,
) -> list[ConceptSuggestion]:
    """Increment suggestion counters. Creates DB rows only — never vault notes."""
    cfg = workspace_config_dict()
    threshold = int(cfg.get("suggestion_threshold") or 5)
    updated: list[ConceptSuggestion] = []
    seen: set[str] = set()
    for raw in entities:
        name = (raw or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        # Skip if a Concept KO already exists with this title
        existing_concept = (
            db.query(KnowledgeObject)
            .filter(
                KnowledgeObject.workspace_role == "concept",
                KnowledgeObject.title == name,
            )
            .first()
        )
        if existing_concept:
            continue

        row = (
            db.query(ConceptSuggestion)
            .filter(
                ConceptSuggestion.entity_key == key,
                ConceptSuggestion.status == "pending",
            )
            .first()
        )
        if row:
            row.mention_count = int(row.mention_count or 0) + 1
            row.entity_name = name[:200]
            if notebook_id and not row.notebook_id:
                row.notebook_id = notebook_id
        else:
            row = ConceptSuggestion(
                id=new_id("sug"),
                notebook_id=notebook_id,
                entity_name=name[:200],
                entity_key=key,
                mention_count=1,
                status="pending",
                message="",
            )
            db.add(row)
        row.message = (
            f'"{row.entity_name}" has appeared {row.mention_count} times. '
            "Would you like to create a permanent Concept note?"
        )
        if row.mention_count >= threshold:
            updated.append(row)
    db.commit()
    return updated


def list_concept_suggestions(
    db: Session,
    *,
    notebook_id: str | None = None,
    pending_only: bool = True,
    min_count: int | None = None,
) -> list[ConceptSuggestion]:
    cfg = workspace_config_dict()
    threshold = int(min_count if min_count is not None else (cfg.get("suggestion_threshold") or 5))
    q = db.query(ConceptSuggestion)
    if pending_only:
        q = q.filter(ConceptSuggestion.status == "pending")
    if notebook_id:
        q = q.filter(
            (ConceptSuggestion.notebook_id == notebook_id)
            | (ConceptSuggestion.notebook_id.is_(None))
        )
    q = q.filter(ConceptSuggestion.mention_count >= threshold)
    return q.order_by(ConceptSuggestion.mention_count.desc()).all()


def promote(
    db: Session,
    ko: KnowledgeObject,
    role: str,
    *,
    title: str | None = None,
    vault_path: str | None = None,
    sync: bool = True,
) -> KnowledgeObject:
    """Promote a Resource (or any KO) into a cognitive vault note.

    Accepts V1.1 roles (information/thinking/research) and legacy aliases
    (concept/project/reflection/book/insight), which remap to cognitive folders
    at sync time.
    """
    role = (role or "").strip().lower()
    if role not in PROMOTE_ROLES:
        raise ValueError(f"role must be one of {sorted(PROMOTE_ROLES)}")
    stage_map = {
        "concept": "concept",
        "project": "project",
        "reflection": "reflection",
        "thinking": "reflection",
        "book": "knowledge_object",
        "information": "knowledge_object",
        "insight": "insight",
        "research": "insight",
    }
    to_stage = stage_map.get(role, role)
    to_maturity = "emerging" if role == "concept" else (ko.maturity or "")

    ko.workspace_role = role
    if role == "book":
        ko.kind = "book" if ko.kind != "book" else ko.kind
    elif role == "information":
        # Keep media kind (article/paper/…) when promoting into Information
        if not ko.kind or ko.kind in {"resource", "other"}:
            ko.kind = "article"
    elif role in {"thinking", "research"}:
        if role == "thinking" and ko.kind not in {"reflection", "question", "concept"}:
            ko.kind = "reflection"
        if role == "research" and ko.kind not in {"insight"}:
            ko.kind = "insight"
    elif role not in {"insight"}:
        ko.kind = role if role != "book" else ko.kind
    ko.graph_eligible = graph_eligible_for_role(role)
    if title:
        ko.title = title.strip()
    ko.status = "ready"
    tags = loads(ko.tags_json, []) or []
    ko.tags_json = dumps(normalize_filter_tags(tags))
    db.commit()
    db.refresh(ko)

    life_svc.advance(
        db,
        ko,
        to_stage,
        trigger="user_promote",
        actor="user",
        to_maturity=to_maturity if role == "concept" else None,
        payload={"workspace_role": role},
    )
    db.refresh(ko)

    if role == "concept":
        life_svc.ensure_concept_profile(db, ko)
        key = ko.title.strip().lower()
        sug = (
            db.query(ConceptSuggestion)
            .filter(
                ConceptSuggestion.entity_key == key,
                ConceptSuggestion.status == "pending",
            )
            .first()
        )
        if sug:
            sug.status = "accepted"
            db.commit()
        life_svc.recompute_concept_scores(db, ko)
    if role == "project":
        life_svc.ensure_project_profile(db, ko)
    if role in {"reflection", "thinking"}:
        from ..db import Reflection

        if not db.query(Reflection).filter(Reflection.id == ko.id).first():
            db.add(
                Reflection(
                    id=ko.id,
                    body_md=ko.summary or "",
                    author="",
                    importance="medium",
                    status="active",
                )
            )
            db.commit()

    if sync:
        from . import workspace as workspace_svc

        vault = vault_path
        if not vault:
            from ..config import get_settings

            vault = get_settings().default_vault_path or None
        if vault:
            # First materialization of thinking should write body; later syncs preserve.
            workspace_svc.sync_note(
                db,
                ko,
                vault_path=vault,
                force=(role in {"reflection", "thinking"}),
            )
            db.refresh(ko)
    return ko


def demote(
    db: Session,
    ko: KnowledgeObject,
    *,
    archive_file: bool = True,
    vault_path: str | None = None,
) -> KnowledgeObject:
    """Remove from thinking graph surface; keep Lake + DB. Optionally move note to Archive/."""
    old_path = ko.vault_path
    ko.workspace_role = "archived"
    ko.graph_eligible = 0
    db.commit()

    if archive_file and old_path:
        from . import workspace as workspace_svc
        from ..config import get_settings

        vault = vault_path or get_settings().default_vault_path
        if vault:
            new_rel = workspace_svc.archive_note(vault, old_path)
            ko.vault_path = new_rel
            db.commit()
    db.refresh(ko)
    return ko


def create_concept_from_suggestion(
    db: Session,
    suggestion: ConceptSuggestion,
    *,
    vault_path: str | None = None,
    notebook_id: str | None = None,
) -> KnowledgeObject:
    """Accept a suggestion: create Concept KO + sync Obsidian note."""
    nb = notebook_id or suggestion.notebook_id
    if not nb:
        raise ValueError("notebook_id is required to create a concept from suggestion")
    ko = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=nb,
        source_doc_id=None,
        kind="concept",
        title=suggestion.entity_name,
        summary="",
        key_points_json="[]",
        language="",
        reading_status="unread",
        importance="medium",
        status="ready",
        source_url=None,
        authors=None,
        published_at=None,
        connector="manual",
        content_hash=content_hash_safe(suggestion.entity_name),
        tags_json="[]",
        entities_json="[]",
        metadata_json=dumps({"from_suggestion_id": suggestion.id}),
        workspace_role="resource",
        graph_eligible=0,
        lifecycle_stage="concept",
        maturity="candidate",
        lifecycle_updated_at=utcnow(),
    )
    db.add(ko)
    suggestion.status = "accepted"
    db.commit()
    db.refresh(ko)
    life_svc.ensure_concept_profile(db, ko)
    return promote(db, ko, "concept", vault_path=vault_path, sync=True)


def content_hash_safe(text: str) -> str:
    from ..utils import content_hash

    return content_hash(text)


def get_by_source(db: Session, source_doc_id: str) -> KnowledgeObject | None:
    return (
        db.query(KnowledgeObject)
        .filter(KnowledgeObject.source_doc_id == source_doc_id)
        .first()
    )


def get_by_id(db: Session, ko_id: str) -> KnowledgeObject | None:
    return db.query(KnowledgeObject).filter(KnowledgeObject.id == ko_id).first()


def list_for_notebook(db: Session, notebook_id: str) -> list[KnowledgeObject]:
    return (
        db.query(KnowledgeObject)
        .filter(KnowledgeObject.notebook_id == notebook_id)
        .order_by(KnowledgeObject.created_at.asc())
        .all()
    )


def list_workspace_notes(db: Session, notebook_id: str | None = None) -> list[KnowledgeObject]:
    q = db.query(KnowledgeObject).filter(
        KnowledgeObject.workspace_role.in_(list(WORKSPACE_NOTE_ROLES))
    )
    if notebook_id:
        q = q.filter(KnowledgeObject.notebook_id == notebook_id)
    return q.order_by(KnowledgeObject.updated_at.desc()).all()


def existing_workspace_titles(db: Session, *, notebook_id: str | None = None) -> set[str]:
    rows = list_workspace_notes(db, notebook_id)
    return {r.title.strip() for r in rows if r.title and r.workspace_role != "report"}


def related_topic_names(db: Session, ko: KnowledgeObject, *, max_n: int = 8) -> list[str]:
    """Only names that already exist as workspace notes (no graph pollution)."""
    existing = existing_workspace_titles(db, notebook_id=ko.notebook_id)
    entities = loads(ko.entities_json, []) or []
    out: list[str] = []
    for e in entities:
        name = str(e).strip()
        if name and name in existing and name not in out:
            out.append(name)
        if len(out) >= max_n:
            break
    return out


def build_links_from_entities(
    db: Session,
    ko: KnowledgeObject,
    entities: list[str],
    *,
    max_links: int = 8,
) -> list[KoLink]:
    """Deprecated for auto-graph: keep DB links for search, but workspace won't auto-wikilink."""
    db.query(KoLink).filter(
        KoLink.from_ko_id == ko.id,
        KoLink.link_type == "related_concept",
    ).delete(synchronize_session=False)
    created: list[KoLink] = []
    seen: set[str] = set()
    for raw in entities:
        name = (raw or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        link = KoLink(
            id=new_id("kl"),
            from_ko_id=ko.id,
            to_name=name[:200],
            to_ko_id=None,
            link_type="related_concept",
        )
        db.add(link)
        created.append(link)
        if len(created) >= max_links:
            break
    db.commit()
    return created


def _map_status(source_status: str) -> str:
    mapping = {
        "ready": "captured",
        "analyzed": "ready",
        "partial": "processing",
        "failed": "failed",
    }
    return mapping.get(source_status, "captured")


def _guess_language(meta: dict) -> str:
    lang = meta.get("language") or meta.get("lang") or ""
    if isinstance(lang, list) and lang:
        return str(lang[0])
    return str(lang) if lang else ""
