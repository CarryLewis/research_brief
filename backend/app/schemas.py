from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None

    model_config = {"populate_by_name": True}


class PubMedConnectorSpec(BaseModel):
    query: str = ""
    max_results: int = 20


class RssConnectorSpec(BaseModel):
    feeds: list[str] = Field(default_factory=list)
    max_per_feed: int = 10


class EmailConnectorSpec(BaseModel):
    labels: list[str] = Field(default_factory=list)
    from_allowlist: list[str] = Field(default_factory=list)
    max_results: int = 20
    days_back: int = 30


class WebConnectorSpec(BaseModel):
    urls: list[str] = Field(default_factory=list)


class WeChatConnectorSpec(BaseModel):
    account: str = ""
    urls: list[str] = Field(default_factory=list)
    max_articles: int = 5
    discover: bool = True


class CustomChannel(BaseModel):
    id: str = ""
    name: str = ""
    kind: str = "rss"  # rss | web | wechat
    url: str = ""
    enabled: bool = True


class ConnectorSpecs(BaseModel):
    pubmed: PubMedConnectorSpec = Field(default_factory=PubMedConnectorSpec)
    rss: RssConnectorSpec = Field(default_factory=RssConnectorSpec)
    email: EmailConnectorSpec = Field(default_factory=EmailConnectorSpec)
    web: WebConnectorSpec = Field(default_factory=WebConnectorSpec)
    wechat: WeChatConnectorSpec = Field(default_factory=WeChatConnectorSpec)


class ScopeSpec(BaseModel):
    topic: str = ""
    language: list[str] = Field(default_factory=lambda: ["zh", "en"])
    time_range: TimeRange = Field(default_factory=TimeRange)
    must_include: list[str] = Field(default_factory=list)
    must_exclude: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(
        default_factory=lambda: ["manual", "pubmed", "rss", "email", "web", "wechat"]
    )
    selected_channels: list[str] = Field(default_factory=lambda: ["pubmed"])
    custom_channels: list[CustomChannel] = Field(default_factory=list)
    connectors: ConnectorSpecs = Field(default_factory=ConnectorSpecs)


class AnalysisSpec(BaseModel):
    brief_template: str = "evidence_brief"
    citation_style: str = "numbered"
    max_sources_in_brief: int = 20
    require_grounding: bool = True
    output_language: str = "zh"
    sections: list[str] = Field(
        default_factory=lambda: [
            "key_takeaways",
            "evidence_map",
            "disagreements",
            "open_questions",
            "source_appendix",
        ]
    )


class NotebookCreate(BaseModel):
    title: str
    topic: str = ""
    scope: ScopeSpec | None = None
    analysis: AnalysisSpec | None = None
    vault_path: str | None = None


class NotebookUpdate(BaseModel):
    title: str | None = None
    topic: str | None = None
    scope: ScopeSpec | None = None
    analysis: AnalysisSpec | None = None
    vault_path: str | None = None


class NotebookOut(BaseModel):
    id: str
    title: str
    topic: str
    scope: ScopeSpec
    analysis: AnalysisSpec
    vault_path: str | None
    created_at: datetime
    updated_at: datetime
    source_count: int = 0


class ManualImportIn(BaseModel):
    title: str
    text: str
    url: str | None = None
    authors: str | None = None
    published_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceOut(BaseModel):
    id: str
    notebook_id: str
    connector: str
    title: str
    url: str | None
    authors: str | None
    published_at: str | None
    raw_text: str
    content_hash: str
    status: str
    error: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    excerpt: str = ""


class IngestRequest(BaseModel):
    connectors: list[str] | None = None
    channel_ids: list[str] | None = None


class IngestResult(BaseModel):
    added: int
    skipped_duplicates: int
    failed: int
    sources: list[SourceOut]


class ExportRequest(BaseModel):
    vault_path: str | None = None
    download_media: bool = True


class ExportResult(BaseModel):
    path: str
    brief_path: str
    sources_written: int


class CollectRequest(BaseModel):
    title: str = ""
    topic: str
    vault_path: str | None = None
    channel_ids: list[str] | None = None
    scope: ScopeSpec | None = None
    download_media: bool = True
    urls: list[str] = Field(default_factory=list)
    feeds: list[str] = Field(default_factory=list)
    pubmed_query: str | None = None
    wechat_account: str | None = None
    wechat_urls: list[str] = Field(default_factory=list)


class CollectResult(BaseModel):
    notebook_id: str
    topic: str
    added: int
    skipped_duplicates: int
    failed: int
    vault_path: str
    index_path: str
    sources_written: int


class InboundEmailIn(BaseModel):
    message_id: str | None = None
    from_: str = Field(default="", alias="from")
    to: str = ""
    subject: str = "(No subject)"
    text: str | None = None
    html: str | None = None
    received_at: str | None = None

    model_config = {"populate_by_name": True}


class AnalysisOut(BaseModel):
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    followup_urls: list[str] = Field(default_factory=list)


class InboundEmailResult(BaseModel):
    notebook_id: str
    email_source_id: str | None = None
    article_ids: list[str] = Field(default_factory=list)
    duplicate: bool = False
    rejected: bool = False
    reject_reason: str | None = None
    subscription_id: str | None = None
    subscription_name: str | None = None
    added: int = 0
    skipped_duplicates: int = 0
    failed: int = 0
    selected_urls: list[str] = Field(default_factory=list)
    analysis: AnalysisOut | None = None
    analysis_error: str | None = None
    vault_path: str | None = None
    index_path: str | None = None


class SubscriptionCreate(BaseModel):
    name: str
    sender_pattern: str
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class SubscriptionUpdate(BaseModel):
    name: str | None = None
    sender_pattern: str | None = None
    enabled: bool | None = None
    tags: list[str] | None = None
    notes: str | None = None


class SubscriptionOut(BaseModel):
    id: str
    name: str
    sender_pattern: str
    enabled: bool
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    created_at: datetime
    updated_at: datetime


class DigestRequest(BaseModel):
    period: str = "daily"  # daily | weekly
    notebook_id: str | None = None
    send: bool = True
    dry_run: bool = False


class DigestResult(BaseModel):
    digest_id: str
    notebook_id: str
    period: str
    period_start: datetime
    period_end: datetime
    subject: str
    content_md: str
    source_count: int
    source_ids: list[str] = Field(default_factory=list)
    status: str
    sent_to: str | None = None
    error: str | None = None


class SearchRequest(BaseModel):
    notebook_id: str
    query: str
    top_k: int = 8


class SearchHit(BaseModel):
    chunk_id: str
    source_id: str
    title: str
    url: str | None = None
    score: float
    excerpt: str
    chunk_index: int = 0


class SearchResult(BaseModel):
    hits: list[SearchHit] = Field(default_factory=list)


class AskRequest(BaseModel):
    notebook_id: str
    question: str
    top_k: int = 6
    save_brief: bool = False


class CitationOut(BaseModel):
    source_id: str
    title: str
    url: str | None = None
    excerpt: str = ""


class AskResult(BaseModel):
    answer: str
    citations: list[CitationOut] = Field(default_factory=list)
    message_id: str | None = None
    brief_id: str | None = None


class PromoteRequest(BaseModel):
    role: str  # concept | project | reflection | book
    title: str | None = None
    vault_path: str | None = None
    sync: bool = True


class DemoteRequest(BaseModel):
    vault_path: str | None = None
    archive_file: bool = True


class KnowledgeObjectOut(BaseModel):
    id: str
    notebook_id: str
    kind: str
    workspace_role: str
    graph_eligible: bool
    title: str
    summary: str = ""
    source_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    vault_path: str | None = None
    status: str = ""
    lifecycle_stage: str = "resource"
    evidence_score: float = 0.0
    confidence: float = 0.0
    maturity: str = ""


class ConceptSuggestionOut(BaseModel):
    id: str
    notebook_id: str | None = None
    entity_name: str
    mention_count: int
    status: str
    message: str = ""


class AcceptSuggestionRequest(BaseModel):
    notebook_id: str | None = None
    vault_path: str | None = None


class ReflectionCreate(BaseModel):
    notebook_id: str
    title: str
    body_md: str = ""
    author: str = ""
    importance: str = "medium"
    related_ko_ids: list[str] = Field(default_factory=list)
    vault_path: str | None = None
    sync: bool = True


class ReflectionUpdate(BaseModel):
    title: str | None = None
    body_md: str | None = None
    importance: str | None = None
    status: str | None = None
    vault_path: str | None = None
    sync: bool = True


class QuestionCreate(BaseModel):
    notebook_id: str
    statement: str
    title: str | None = None
    priority: str = "P2"
    owner: str = ""
    related_ko_ids: list[str] = Field(default_factory=list)


class QuestionUpdate(BaseModel):
    statement: str | None = None
    status: str | None = None
    priority: str | None = None
    answer_summary: str | None = None


class InsightCreate(BaseModel):
    notebook_id: str
    statement: str
    evidence_md: str = ""
    confidence: float = 0.5
    title: str | None = None
    supporting_ko_ids: list[str] = Field(default_factory=list)
    answers_question_id: str | None = None
    vault_path: str | None = None
    sync_as_reflection: bool = False


class LifecycleEventOut(BaseModel):
    id: str
    ko_id: str
    from_stage: str
    to_stage: str
    from_maturity: str = ""
    to_maturity: str = ""
    trigger: str
    actor: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class LifecycleProposalOut(BaseModel):
    id: str
    ko_id: str
    notebook_id: str | None = None
    proposed_stage: str
    proposed_maturity: str
    reason: str
    score: float
    status: str


class AcceptProposalRequest(BaseModel):
    vault_path: str | None = None
    sync_workspace: bool = True


class ConceptCentralOut(BaseModel):
    id: str
    title: str
    maturity_level: str
    promotion_score: float
    mention_count: int
    reflection_count: int
    resource_count: int
    project_count: int


class ReflectionOut(BaseModel):
    id: str
    title: str
    body_md: str
    author: str
    importance: str
    status: str
    vault_path: str | None = None


class QuestionOut(BaseModel):
    id: str
    title: str
    statement: str
    status: str
    priority: str
    owner: str = ""
    answer_summary: str = ""


class InsightOut(BaseModel):
    id: str
    title: str
    statement: str
    evidence_md: str
    confidence: float
    status: str


class SignalFilterRequest(BaseModel):
    apply: bool = False
    use_llm: bool = True


class SignalFilterResult(BaseModel):
    ko_id: str
    decision: str
    reason: str
    confidence: float = 0.0
    applied: bool = False
    actor: str = "system"


class ReflectionAssistRequest(BaseModel):
    create_questions: bool = False
    use_llm: bool = True


class InsightDraftRequest(BaseModel):
    notebook_id: str
    supporting_ko_ids: list[str] = Field(default_factory=list)
    question_id: str | None = None
    use_llm: bool = True
    accept: bool = False


class GraphSyncRequest(BaseModel):
    notebook_id: str | None = None


class GraphSuggestLinksRequest(BaseModel):
    notebook_id: str
    use_llm: bool = False


class LibrarySaveRequest(BaseModel):
    """Save a page into the Obsidian Library (v1 Capture).

    Prefer ``html`` from the browser extension (logged-in / paywalled DOM).
    ``url`` alone falls back to server-side fetch (public pages only).
    ``body_md`` skips HTML parsing when the client already has Markdown.
    """

    url: str | None = None
    html: str | None = None
    body_md: str | None = None
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source_type: str = "article"  # article | email
    visibility: str = "private"
    status: str = "inbox"
    download_images: bool = True
    on_duplicate: str = "update"  # update | skip | new
    vault_path: str | None = None


class LibrarySaveResult(BaseModel):
    ok: bool = True
    item_id: str
    title: str
    note_path: str
    note_relpath: str
    source_url: str | None = None
    created: bool = False
    updated: bool = False
    skipped: bool = False
    images_downloaded: int = 0
    image_errors: list[str] = Field(default_factory=list)
    vault_path: str = ""


class ThinkingSyncRequest(BaseModel):
    vault_path: str | None = None
    soft_archive_missing: bool = True


class ThinkingSyncItemOut(BaseModel):
    source_id: str
    title: str = ""
    vault_path: str = ""
    action: str = ""


class ThinkingSyncResult(BaseModel):
    ok: bool = True
    created: int = 0
    updated: int = 0
    renamed: int = 0
    unchanged: int = 0
    archived: int = 0
    errors: list[str] = Field(default_factory=list)
    items: list[ThinkingSyncItemOut] = Field(default_factory=list)


class ThinkingSyncStatusOut(BaseModel):
    active: int = 0
    archived: int = 0
    total: int = 0
    last_synced_at: str | None = None
