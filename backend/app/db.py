from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from .config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Notebook(Base):
    __tablename__ = "notebooks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    topic: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    scope_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    analysis_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    vault_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    sources: Mapped[list["SourceDoc"]] = relationship(
        back_populates="notebook", cascade="all, delete-orphan"
    )
    briefs: Mapped[list["Brief"]] = relationship(
        back_populates="notebook", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="notebook", cascade="all, delete-orphan"
    )


class SourceDoc(Base):
    __tablename__ = "source_docs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notebook_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notebooks.id", ondelete="CASCADE"), index=True
    )
    connector: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    title: Mapped[str] = mapped_column(String(1024), nullable=False, default="Untitled")
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    authors: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    notebook: Mapped["Notebook"] = relationship(back_populates="sources")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notebook_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notebooks.id", ondelete="CASCADE"), index=True
    )
    doc_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_docs.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Lightweight lexical bag for retrieval (space-separated tokens)
    tokens: Mapped[str] = mapped_column(Text, nullable=False, default="")

    source: Mapped["SourceDoc"] = relationship(back_populates="chunks")


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notebook_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notebooks.id", ondelete="CASCADE"), index=True
    )
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    citations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_current: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    notebook: Mapped["Notebook"] = relationship(back_populates="briefs")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notebook_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notebooks.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    notebook: Mapped["Notebook"] = relationship(back_populates="messages")


class Subscription(Base):
    """Catalog entry for newsletter senders managed at the command/API entry."""

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    sender_pattern: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DigestRun(Base):
    """Daily/weekly digest generation + delivery record."""

    __tablename__ = "digest_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notebook_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notebooks.id", ondelete="CASCADE"), index=True
    )
    period: Mapped[str] = mapped_column(String(32), nullable=False)  # daily | weekly
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subject: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    sent_to: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    # draft | sent | empty | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeObject(Base):
    """Canonical AI-readable Knowledge Object (structured authority in SQLite)."""

    __tablename__ = "knowledge_objects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notebook_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("notebooks.id", ondelete="CASCADE"), index=True
    )
    source_doc_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("source_docs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="article")
    title: Mapped[str] = mapped_column(String(1024), nullable=False, default="Untitled")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    key_points_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    reading_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unread")
    importance: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="captured")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    authors: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connector: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True, default="")
    primary_content_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    entities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # resource | concept | project | reflection | book | report | archived
    workspace_role: Mapped[str] = mapped_column(String(64), nullable=False, default="resource")
    graph_eligible: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vault_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Lifecycle Engine
    # signal | resource | knowledge_object | reflection | concept | project | insight | question | discarded
    lifecycle_stage: Mapped[str] = mapped_column(
        String(64), nullable=False, default="resource", index=True
    )
    evidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # candidate | emerging | stable | core | deprecated (concepts); empty otherwise
    maturity: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    lifecycle_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signal_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # pending | kept | discarded (signals)
    filter_status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    content_objects: Mapped[list["ContentObject"]] = relationship(
        back_populates="knowledge_object", cascade="all, delete-orphan"
    )
    links: Mapped[list["KoLink"]] = relationship(
        back_populates="from_ko",
        foreign_keys="KoLink.from_ko_id",
        cascade="all, delete-orphan",
    )


class ContentObject(Base):
    """Index row for an immutable Content Lake object."""

    __tablename__ = "content_objects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ko_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("knowledge_objects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="original")
    # original | media | derived
    uri: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    mime: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    knowledge_object: Mapped["KnowledgeObject | None"] = relationship(
        back_populates="content_objects"
    )


class KoLink(Base):
    """Typed edge between Knowledge Objects (widened for Lifecycle Engine)."""

    __tablename__ = "ko_links"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    from_ko_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), index=True
    )
    to_name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    to_ko_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("knowledge_objects.id", ondelete="SET NULL"), nullable=True
    )
    # related_to | about | supports | contradicts | reflects_on | member_of | answers | ...
    link_type: Mapped[str] = mapped_column(String(64), nullable=False, default="related_to")
    from_type: Mapped[str] = mapped_column(String(64), nullable=False, default="ko")
    to_type: Mapped[str] = mapped_column(String(64), nullable=False, default="ko")
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    # ai | user | system
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    from_ko: Mapped["KnowledgeObject"] = relationship(
        back_populates="links", foreign_keys=[from_ko_id]
    )


class ConceptSuggestion(Base):
    """AI recommendation to create a permanent Concept note — never an auto file."""

    __tablename__ = "concept_suggestions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notebook_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("notebooks.id", ondelete="CASCADE"), index=True, nullable=True
    )
    entity_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    entity_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # pending | accepted | dismissed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Reflection(Base):
    """First-class human thinking — DB authority; Obsidian is a projection."""

    __tablename__ = "reflections"

    id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), primary_key=True
    )
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    importance: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    # draft | active | archived
    open_questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Question(Base):
    """First-class research question."""

    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), primary_key=True
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="open", index=True)
    # open | investigating | partially_answered | answered | archived
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="P2")
    owner: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    answer_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Insight(Base):
    """Highest-value intellectual synthesis."""

    __tablename__ = "insights"

    id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), primary_key=True
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    # draft | active | challenged | retired
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ConceptProfile(Base):
    """Measurable concept maturity (1:1 with concept KO)."""

    __tablename__ = "concept_profiles"

    ko_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), primary_key=True
    )
    maturity_level: Mapped[str] = mapped_column(
        String(64), nullable=False, default="candidate", index=True
    )
    promotion_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reflection_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resource_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    project_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    persistence_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stable_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    core_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProjectProfile(Base):
    """Project as knowledge hub."""

    __tablename__ = "project_profiles"

    ko_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), primary_key=True
    )
    objectives_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    roadmap_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    knowledge_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    active_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    # active | paused | done
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class LifecycleEvent(Base):
    """Append-only history of intellectual stage changes. Never overwrite."""

    __tablename__ = "lifecycle_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ko_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), index=True
    )
    from_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    to_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    from_maturity: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    to_maturity: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    trigger: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class LifecycleProposal(Base):
    """Pending AI/system-proposed lifecycle transition awaiting human confirm."""

    __tablename__ = "lifecycle_proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ko_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), index=True
    )
    notebook_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    proposed_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    proposed_maturity: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # pending | accepted | dismissed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    # graph_action etc. for Graph Engine proposals (propose-only)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class GraphNode(Base):
    """Materialized cognitive graph node (rebuildable projection)."""

    __tablename__ = "graph_nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # = ko_id
    notebook_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    layer: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    label: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    maturity: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    degree: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    community_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    lifecycle_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    attrs_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class GraphEdge(Base):
    """Materialized cognitive graph edge (resolved endpoints only)."""

    __tablename__ = "graph_edges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notebook_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    from_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    to_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    edge_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    source_link_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GraphCommunity(Base):
    __tablename__ = "graph_communities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notebook_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attrs_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class GraphMetricsSnapshot(Base):
    __tablename__ = "graph_metrics_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notebook_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class GraphSyncRun(Base):
    __tablename__ = "graph_sync_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notebook_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    community_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


_settings = get_settings()
engine = create_engine(
    f"sqlite:///{_settings.db_path}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _add_column_if_missing(conn, table: str, column: str, ddl: str) -> None:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    cols = {r[1] for r in rows}
    if column not in cols:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def _migrate_sqlite_columns() -> None:
    """Add Constitution + Lifecycle columns to existing SQLite DBs."""
    with engine.begin() as conn:
        try:
            rows = conn.execute(text("PRAGMA table_info(knowledge_objects)")).fetchall()
        except Exception:  # noqa: BLE001
            return
        if not rows:
            return
        ko_alters = [
            ("workspace_role", "workspace_role VARCHAR(64) NOT NULL DEFAULT 'resource'"),
            ("graph_eligible", "graph_eligible INTEGER NOT NULL DEFAULT 0"),
            ("lifecycle_stage", "lifecycle_stage VARCHAR(64) NOT NULL DEFAULT 'resource'"),
            ("evidence_score", "evidence_score FLOAT NOT NULL DEFAULT 0"),
            ("confidence", "confidence FLOAT NOT NULL DEFAULT 0"),
            ("maturity", "maturity VARCHAR(64) NOT NULL DEFAULT ''"),
            ("lifecycle_updated_at", "lifecycle_updated_at DATETIME"),
            ("signal_expires_at", "signal_expires_at DATETIME"),
            ("filter_status", "filter_status VARCHAR(32) NOT NULL DEFAULT ''"),
        ]
        for col, ddl in ko_alters:
            _add_column_if_missing(conn, "knowledge_objects", col, ddl)

        try:
            link_rows = conn.execute(text("PRAGMA table_info(ko_links)")).fetchall()
        except Exception:  # noqa: BLE001
            link_rows = []
        if link_rows:
            for col, ddl in [
                ("from_type", "from_type VARCHAR(64) NOT NULL DEFAULT 'ko'"),
                ("to_type", "to_type VARCHAR(64) NOT NULL DEFAULT 'ko'"),
                ("weight", "weight FLOAT NOT NULL DEFAULT 1"),
                ("evidence", "evidence TEXT NOT NULL DEFAULT ''"),
                ("created_by", "created_by VARCHAR(32) NOT NULL DEFAULT 'system'"),
            ]:
                _add_column_if_missing(conn, "ko_links", col, ddl)

        try:
            prop_rows = conn.execute(text("PRAGMA table_info(lifecycle_proposals)")).fetchall()
        except Exception:  # noqa: BLE001
            prop_rows = []
        if prop_rows:
            _add_column_if_missing(
                conn,
                "lifecycle_proposals",
                "payload_json",
                "payload_json TEXT NOT NULL DEFAULT '{}'",
            )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
