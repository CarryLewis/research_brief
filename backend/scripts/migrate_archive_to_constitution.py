#!/usr/bin/env python3
"""Migrate all Archive vault dumps into Constitution framework.

Rules:
- Content → Content Lake + Resource KO (never re-create Inbox dumps)
- Group into Project hubs by capture theme
- Curated Concepts only for major themes (not one Concept per paper)
- Archive files remain cold storage; Collections gets a human index MOC
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.config import get_settings  # noqa: E402
from app.db import KnowledgeObject, KoLink, Notebook, SessionLocal, SourceDoc, init_db, utcnow  # noqa: E402
from app.schemas import AnalysisOut  # noqa: E402
from app.services import graph_engine as graph_svc  # noqa: E402
from app.services import knowledge as knowledge_svc  # noqa: E402
from app.services import lifecycle as life_svc  # noqa: E402
from app.services import thinking as thinking_svc  # noqa: E402
from app.services import workspace as workspace_svc  # noqa: E402
from app.utils import content_hash, dumps, loads, new_id  # noqa: E402

SKIP_NAMES = {"readme.md", "_index.md"}
SKIP_TITLE_RE = re.compile(r"^(example domain|untitled)$", re.I)

# Stable notebook / project titles
THEMES = {
    "migraine": {
        "notebook_id": "nb_a519e4963d75",
        "notebook_title": "Nature migraine research",
        "project_title": "Nature Migraine Research",
        "concepts": [("Migraine", "core")],
    },
    "kazke_ai": {
        "notebook_id": "nb_archive_kazke",
        "notebook_title": "AI Agents · 数字生命卡兹克",
        "project_title": "AI Agents Reading",
        "concepts": [
            ("Agent", "emerging"),
            ("Design Agent", "emerging"),
            ("LLM", "emerging"),
        ],
    },
    "pubmed_legacy": {
        "notebook_id": "nb_archive_pubmed",
        "notebook_title": "Legacy PubMed captures",
        "project_title": "Legacy PubMed Captures",
        "concepts": [],
    },
    "misc": {
        "notebook_id": "nb_archive_misc",
        "notebook_title": "Legacy email & web",
        "project_title": "Legacy Email & Web",
        "concepts": [],
    },
}


def _parse_md(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta: dict = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1]) or {}
            except Exception:  # noqa: BLE001
                meta = {}
            body = parts[2]
    # Prefer quote block body for raw-text exports
    m = re.search(r"> \[!quote\].*?\n>((?:.|\n)*?)(?:\n## |\n---|\Z)", body)
    if m:
        quoted = m.group(1)
        lines = []
        for line in quoted.splitlines():
            lines.append(re.sub(r"^>\s?", "", line))
        extracted = "\n".join(lines).strip()
        if len(extracted) > 80:
            body = extracted
    # Strip callout markers leftover
    body = re.sub(r"^>\s?", "", body, flags=re.M)
    return meta if isinstance(meta, dict) else {}, body.strip()


def _connector_from_path(path: Path, meta: dict) -> str:
    c = (meta.get("connector") or "").lower()
    if c:
        return c
    name = path.name.lower()
    for prefix in ("pubmed", "wechat", "web", "email", "rss"):
        if f"_{prefix}_" in name or name.startswith(f"{prefix}_") or f"/{prefix}_" in str(path).lower():
            # filename like 01_pubmed_Title.md
            if f"_{prefix}_" in name or name.startswith(prefix):
                return prefix
    typ = (meta.get("type") or "").lower()
    if typ == "paper":
        return "pubmed"
    if "wechat" in typ or "微信" in str(meta):
        return "wechat"
    return "manual"


def _theme_for(path: Path, meta: dict, title: str, connector: str) -> str:
    p = str(path)
    topic = str(meta.get("tags") or "") + str(meta.get("keywords") or "")
    blob = f"{p} {title} {topic}".lower()
    if "preconstitution" in p.lower() or "migraine" in blob:
        return "migraine"
    if "数字生命卡兹克" in blob or "kazke" in blob or connector == "wechat":
        return "kazke_ai"
    if "anthropic" in blob or "claude" in blob or "gpt-" in blob or "agent" in blob:
        if "pubmed" not in blob:
            return "kazke_ai"
    if connector == "pubmed" or "pubmed" in p.lower():
        return "pubmed_legacy"
    return "misc"


def collect_archive_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        archive = root / "Archive"
        if not archive.is_dir():
            continue
        for path in archive.rglob("*.md"):
            if path.name.lower() in SKIP_NAMES:
                continue
            # Prefer text/ payloads; also PreConstitution root md
            rel = str(path.relative_to(archive))
            if "/media/" in rel.replace("\\", "/"):
                continue
            key = path.name.lower()
            # Prefer longer file if duplicate names
            if key in seen:
                # keep both if different paths with same name — use full path hash
                key = content_hash(str(path))
            seen.add(key)
            files.append(path)
    # Dedupe by absolute resolved path
    uniq = {}
    for f in files:
        uniq[str(f.resolve())] = f
    return sorted(uniq.values(), key=lambda p: str(p))


def ensure_notebook(db, theme_key: str) -> Notebook:
    cfg = THEMES[theme_key]
    nb = db.query(Notebook).filter(Notebook.id == cfg["notebook_id"]).first()
    if nb:
        nb.title = cfg["notebook_title"]
        db.commit()
        return nb
    nb = Notebook(
        id=cfg["notebook_id"],
        title=cfg["notebook_title"],
        topic=theme_key,
        scope_json=dumps({"from_archive": True}),
    )
    db.add(nb)
    db.commit()
    return nb


def ensure_project(db, theme_key: str, vault: str) -> KnowledgeObject:
    cfg = THEMES[theme_key]
    ensure_notebook(db, theme_key)
    title = cfg["project_title"]
    ko = (
        db.query(KnowledgeObject)
        .filter(
            KnowledgeObject.notebook_id == cfg["notebook_id"],
            KnowledgeObject.workspace_role == "project",
            KnowledgeObject.title == title,
        )
        .first()
    )
    if ko:
        workspace_svc.sync_note(db, ko, vault_path=vault)
        return ko
    ko = KnowledgeObject(
        id=new_id("ko"),
        notebook_id=cfg["notebook_id"],
        kind="project",
        title=title,
        summary=f"Project hub for archive migration theme: {theme_key}.",
        key_points_json=dumps(
            [
                "Resources live in the Knowledge Database / Content Lake",
                "Archive/ files are cold backups only",
                "Promote Concepts deliberately",
            ]
        ),
        status="ready",
        connector="manual",
        content_hash=new_id("h"),
        tags_json=dumps(["research"]),
        entities_json="[]",
        metadata_json=dumps({"from_archive": True, "theme": theme_key}),
        workspace_role="project",
        graph_eligible=1,
        lifecycle_stage="project",
        lifecycle_updated_at=utcnow(),
    )
    db.add(ko)
    db.commit()
    life_svc.ensure_project_profile(db, ko)
    life_svc.record_event(
        db, ko, from_stage="", to_stage="project", trigger="user_promote", actor="user",
        payload={"archive_migration": True},
    )
    workspace_svc.sync_note(db, ko, vault_path=vault)
    return ko


def ensure_concepts(db, theme_key: str, vault: str, project: KnowledgeObject) -> list[KnowledgeObject]:
    out = []
    cfg = THEMES[theme_key]
    for name, maturity in cfg.get("concepts") or []:
        c = (
            db.query(KnowledgeObject)
            .filter(
                KnowledgeObject.notebook_id == cfg["notebook_id"],
                KnowledgeObject.kind == "concept",
                KnowledgeObject.title == name,
            )
            .first()
        )
        if not c:
            c = KnowledgeObject(
                id=new_id("ko"),
                notebook_id=cfg["notebook_id"],
                kind="concept",
                title=name,
                summary=f"Concept curated from archive migration ({theme_key}).",
                key_points_json="[]",
                status="ready",
                connector="manual",
                content_hash=new_id("h"),
                tags_json=dumps(["research", "ai"] if theme_key == "kazke_ai" else ["medicine", "research"]),
                entities_json=dumps([name]),
                metadata_json=dumps({"from_archive": True}),
                workspace_role="concept",
                graph_eligible=1,
                lifecycle_stage="concept",
                maturity=maturity,
                confidence=0.55,
                lifecycle_updated_at=utcnow(),
            )
            db.add(c)
            db.commit()
            life_svc.ensure_concept_profile(db, c)
            life_svc.record_event(
                db, c, from_stage="", to_stage="concept", to_maturity=maturity,
                trigger="user_promote", actor="user", payload={"archive_migration": True},
            )
        else:
            c.workspace_role = "concept"
            c.graph_eligible = 1
            if not c.maturity:
                c.maturity = maturity
            db.commit()
        # edge to project
        exists = (
            db.query(KoLink)
            .filter(
                KoLink.from_ko_id == c.id,
                KoLink.to_ko_id == project.id,
                KoLink.link_type == "member_of",
            )
            .first()
        )
        if not exists:
            life_svc.create_edge(
                db, from_ko_id=c.id, to_ko_id=project.id, edge_type="member_of",
                from_type="concept", to_type="project", created_by="system",
            )
        workspace_svc.sync_note(db, c, vault_path=vault)
        out.append(c)
    return out


def ingest_file(db, path: Path, theme_key: str, project: KnowledgeObject) -> str:
    """Returns created|updated|skipped|error."""
    meta, body = _parse_md(path)
    title = (meta.get("title") or path.stem).strip()
    title = re.sub(r"^\d+_(pubmed|wechat|web|email)_", "", title)
    title = title.replace("_", " ").strip() or path.stem
    if SKIP_TITLE_RE.match(title):
        return "skipped"
    if len(body) < 40 and not meta.get("url"):
        return "skipped"

    connector = _connector_from_path(path, meta)
    url = meta.get("url") or meta.get("source") or None
    if isinstance(url, str):
        url = url.strip() or None
    authors = meta.get("authors") or meta.get("author") or None
    if isinstance(authors, list):
        authors = ", ".join(str(a) for a in authors)

    text_for_hash = body or title
    ch = content_hash(text_for_hash + (url or ""))

    # Dedup by hash or url
    existing_src = (
        db.query(SourceDoc).filter(SourceDoc.content_hash == ch).first()
    )
    if not existing_src and url:
        existing_src = db.query(SourceDoc).filter(SourceDoc.url == url).first()

    nb_id = THEMES[theme_key]["notebook_id"]
    ensure_notebook(db, theme_key)

    if existing_src:
        ko = knowledge_svc.get_by_source(db, existing_src.id)
        if ko:
            if ko.workspace_role in ("resource", "archived", ""):
                ko.notebook_id = nb_id
                ko.workspace_role = "resource"
                ko.graph_eligible = 0
                if ko.vault_path and ("Inbox" in ko.vault_path or "01_Raw" in ko.vault_path):
                    ko.vault_path = None
                db.commit()
            _link_project(db, ko, project)
            return "updated"
        # source without KO — create KO
        ko = knowledge_svc.upsert_from_source(db, existing_src, store_lake=True)
        ko.notebook_id = nb_id
        db.commit()
        _link_project(db, ko, project)
        return "updated"

    src = SourceDoc(
        id=new_id("src"),
        notebook_id=nb_id,
        connector=connector,
        title=title[:1000],
        url=url,
        authors=str(authors) if authors else None,
        published_at=str(meta.get("date") or meta.get("created") or "") or None,
        raw_text=body[:200000],
        content_hash=ch,
        status="ready",
        metadata_json=dumps(
            {
                "from_archive": True,
                "archive_path": str(path),
                "theme": theme_key,
                "type": meta.get("type"),
            }
        ),
    )
    db.add(src)
    db.commit()
    ko = knowledge_svc.upsert_from_source(db, src, store_lake=True)
    ko.notebook_id = nb_id
    ko.workspace_role = "resource"
    ko.graph_eligible = 0
    ko.vault_path = None
    db.commit()
    db.refresh(ko)

    # Archive dumps are already kept history — never leave as ephemeral signals
    if (ko.lifecycle_stage or "") == "signal":
        if not ko.primary_content_uri and body.strip():
            from app.services import content_lake as lake_svc

            ref = lake_svc.put_text(
                body, mime="text/plain", role="original", ko_id=ko.id, filename=f"{ko.id}.txt"
            )
            ko.primary_content_uri = ref.uri
            db.commit()
        life_svc.keep_signal(db, ko, actor="system")
        db.refresh(ko)

    # Light structure
    entities = []
    for term in ("Migraine", "Agent", "LLM", "Claude", "GPT", "Anthropic", "Design Agent", "Stroke"):
        if re.search(re.escape(term), f"{title}\n{body}", re.I):
            entities.append(term)
    summary = body[:500].replace("\n", " ") if body else title
    knowledge_svc.apply_analysis(
        db,
        ko,
        AnalysisOut(
            summary=summary,
            tags=["research"] + (["ai", "technology"] if theme_key == "kazke_ai" else ["medicine"] if theme_key in {"migraine", "pubmed_legacy"} else []),
            key_points=[s.strip() for s in re.split(r"(?<=[.!?。！？])\s+", body) if len(s.strip()) > 40][:4],
            entities=entities[:10],
            followup_urls=[url] if url else [],
        ),
    )
    if (ko.lifecycle_stage or "") == "signal":
        life_svc.keep_signal(db, ko, actor="system")
        db.refresh(ko)
    life_svc.mark_analyzed(db, ko, confidence=0.45)
    ko.workspace_role = "resource"
    ko.graph_eligible = 0
    ko.vault_path = None
    ko.filter_status = "kept"
    db.commit()
    _link_project(db, ko, project)

    # Link to matching concepts by entity
    for ent in entities:
        c = (
            db.query(KnowledgeObject)
            .filter(
                KnowledgeObject.notebook_id == nb_id,
                KnowledgeObject.kind == "concept",
                KnowledgeObject.title == ent,
            )
            .first()
        )
        if c:
            _link_about(db, ko, c)
    return "created"


def _link_project(db, ko: KnowledgeObject, project: KnowledgeObject) -> None:
    exists = (
        db.query(KoLink)
        .filter(
            KoLink.from_ko_id == ko.id,
            KoLink.to_ko_id == project.id,
            KoLink.link_type.in_(("member_of", "about")),
        )
        .first()
    )
    if exists:
        return
    life_svc.create_edge(
        db,
        from_ko_id=ko.id,
        to_ko_id=project.id,
        edge_type="member_of",
        from_type="ko",
        to_type="project",
        created_by="system",
        evidence="archive migration",
    )


def _link_about(db, ko: KnowledgeObject, concept: KnowledgeObject) -> None:
    exists = (
        db.query(KoLink)
        .filter(
            KoLink.from_ko_id == ko.id,
            KoLink.to_ko_id == concept.id,
            KoLink.link_type == "about",
        )
        .first()
    )
    if exists:
        return
    life_svc.create_edge(
        db,
        from_ko_id=ko.id,
        to_ko_id=concept.id,
        edge_type="about",
        from_type="ko",
        to_type="concept",
        created_by="system",
    )


def write_archive_readme(vault: Path, stats: dict) -> None:
    archive = vault / "Archive"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "README.md").write_text(
        f"""---
title: Archive
type: meta
updated: 2026-08-02
---

# Archive (cold storage)

These folders are **historical vault dumps**. They are no longer the system of record.

## Arrangement (Constitution)

| Archive path | Knowledge OS destination |
|--------------|--------------------------|
| `Legacy/01_Raw/**/text` | Content Lake + Resource KOs |
| `PreConstitution-Inbox/` | Resource KOs (papers); thinking notes under Projects/Concepts |
| `Legacy/00_Inbox`, `Legacy/20_Sources` | Retired capture UI — empty shells |

**Do not** re-import these files into Concepts/Projects as bulk notes.

Curated hubs:

- `Projects/Nature Migraine Research`
- `Projects/AI Agents Reading`
- `Projects/Legacy PubMed Captures`
- `Projects/Legacy Email & Web`

See `Collections/Archive Sources Index.md` for counts.

## Migration stats

```json
{dumps(stats)}
```
""",
        encoding="utf-8",
    )


def write_collection_index(vault: Path, stats: dict) -> None:
    collections = vault / "Collections"
    collections.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "title: Archive Sources Index",
        "type: collection",
        "graph: false",
        "updated: 2026-08-02",
        "---",
        "",
        "# Archive Sources Index",
        "",
        "Human-readable map of Archive → Knowledge Database arrangement.",
        "Resources are **not** listed as vault notes.",
        "",
        "## Projects",
        "",
        "- [[Nature Migraine Research]]",
        "- [[AI Agents Reading]]",
        "- [[Legacy PubMed Captures]]",
        "- [[Legacy Email & Web]]",
        "",
        "## Counts by theme",
        "",
        "| Theme | Created | Updated | Skipped |",
        "|-------|---------|---------|---------|",
    ]
    by = stats.get("by_theme") or {}
    for theme, c in sorted(by.items()):
        lines.append(
            f"| {theme} | {c.get('created', 0)} | {c.get('updated', 0)} | {c.get('skipped', 0)} |"
        )
    lines += [
        "",
        f"Total files scanned: **{stats.get('files_scanned', 0)}**",
        "",
        "## Rule",
        "",
        "Open Projects/Concepts/Reflections for thinking.",
        "Use search / Graph API for Resources.",
        "",
    ]
    (collections / "Archive Sources Index.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    init_db()
    settings = get_settings()
    repo_vault = REPO / "vault"
    live_vault = Path(settings.default_vault_path).expanduser() if settings.default_vault_path else None
    roots = [repo_vault]
    if live_vault and live_vault.exists():
        roots.append(live_vault)

    files = collect_archive_files(roots)
    # Prefer live path when same basename+size exists in both — already unique by resolve

    db = SessionLocal()
    stats: dict = {
        "files_scanned": len(files),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "by_theme": defaultdict(lambda: {"created": 0, "updated": 0, "skipped": 0, "errors": 0}),
    }
    target_vault = str(live_vault) if live_vault and live_vault.exists() else str(repo_vault)

    try:
        projects: dict[str, KnowledgeObject] = {}
        for theme in THEMES:
            projects[theme] = ensure_project(db, theme, target_vault)
            ensure_concepts(db, theme, target_vault, projects[theme])

        for path in files:
            meta, _body = _parse_md(path)
            title = str(meta.get("title") or path.stem)
            connector = _connector_from_path(path, meta)
            theme = _theme_for(path, meta, title, connector)
            try:
                result = ingest_file(db, path, theme, projects[theme])
            except Exception as exc:  # noqa: BLE001
                result = "error"
                stats["errors"] += 1
                stats["by_theme"][theme]["errors"] += 1
                print(f"ERR {path}: {exc}", file=sys.stderr)
                continue
            stats[result] = stats.get(result, 0) + 1
            stats["by_theme"][theme][result] = stats["by_theme"][theme].get(result, 0) + 1

        # Opening reflection for kazke if none
        kazke_nb = THEMES["kazke_ai"]["notebook_id"]
        if not (
            db.query(KnowledgeObject)
            .filter(
                KnowledgeObject.notebook_id == kazke_nb,
                KnowledgeObject.lifecycle_stage == "reflection",
            )
            .first()
        ):
            proj = projects["kazke_ai"]
            concepts = (
                db.query(KnowledgeObject)
                .filter(
                    KnowledgeObject.notebook_id == kazke_nb,
                    KnowledgeObject.kind == "concept",
                )
                .all()
            )
            thinking_svc.create_reflection(
                db,
                notebook_id=kazke_nb,
                title="AI Agents archive — opening notes",
                body_md=(
                    "## Archive migration\n\n"
                    "WeChat / web captures from 数字生命卡兹克 are now **Resources** in the DB.\n"
                    "This vault keeps the Project hub and Concepts only.\n\n"
                    "### Concepts\n"
                    "- [[Agent]]\n- [[Design Agent]]\n- [[LLM]]\n\n"
                    "### Open questions\n"
                    "- Which Agent product patterns are durable vs hype?\n"
                    "- How should Design Agents fit a personal Knowledge OS?\n"
                ),
                author="archive-migration",
                related_ko_ids=[proj.id] + [c.id for c in concepts],
                vault_path=target_vault,
                sync=True,
            )

        for theme in THEMES:
            life_svc.evaluate_workspace(db, THEMES[theme]["notebook_id"])
            graph_svc.sync_graph(db, THEMES[theme]["notebook_id"])
            workspace_svc.sync_workspace_notes(
                db, vault_path=target_vault, notebook_id=THEMES[theme]["notebook_id"]
            )

        # Mirror curated notes + meta into repo vault
        if str(repo_vault) != target_vault:
            for theme in THEMES:
                workspace_svc.sync_workspace_notes(
                    db, vault_path=str(repo_vault), notebook_id=THEMES[theme]["notebook_id"]
                )

        stats["by_theme"] = dict(stats["by_theme"])
        for v in roots:
            write_archive_readme(v, stats)
            write_collection_index(v, stats)
            workspace_svc.ensure_scaffold(v)

        # Final global graph sync
        graph_all = graph_svc.sync_graph(db, None)
        stats["graph"] = graph_all
    finally:
        db.close()

    print(dumps(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
