"""Lexical search and grounded Q&A over notebook chunks."""

from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from ..db import Brief, Chunk, Message, SourceDoc
from ..schemas import AskResult, CitationOut, SearchHit, SearchResult
from ..utils import dumps, excerpt, new_id, tokenize
from . import llm as llm_svc


def search(db: Session, notebook_id: str, query: str, top_k: int = 8) -> SearchResult:
    q_tokens = tokenize(query or "")
    if not q_tokens:
        return SearchResult(hits=[])
    q_set = set(q_tokens)
    q_counts = Counter(q_tokens)
    rows = db.query(Chunk).filter(Chunk.notebook_id == notebook_id).all()
    scored: list[tuple[float, Chunk]] = []
    for row in rows:
        c_tokens = (row.tokens or "").split()
        if not c_tokens:
            c_tokens = tokenize(row.text or "")
        c_set = set(c_tokens)
        overlap = q_set & c_set
        if not overlap:
            continue
        # overlap size + TF-ish boost for repeated query terms
        score = float(len(overlap))
        c_counts = Counter(c_tokens)
        for t in overlap:
            score += min(q_counts[t], c_counts[t]) * 0.25
        # slight boost for denser matches
        score += len(overlap) / max(len(q_set), 1)
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    hits: list[SearchHit] = []
    for score, row in scored[: max(1, top_k)]:
        src = db.get(SourceDoc, row.doc_id)
        hits.append(
            SearchHit(
                chunk_id=row.id,
                source_id=row.doc_id,
                title=(src.title if src else "Untitled"),
                url=(src.url if src else None),
                score=round(score, 4),
                excerpt=excerpt(row.text or "", 280),
                chunk_index=row.chunk_index,
            )
        )
    return SearchResult(hits=hits)


def ask(
    db: Session,
    notebook_id: str,
    question: str,
    *,
    top_k: int = 6,
    save_brief: bool = False,
    output_language: str = "zh",
) -> AskResult:
    result = search(db, notebook_id, question, top_k=top_k)
    citations: list[CitationOut] = []
    seen_sources: set[str] = set()
    context_blocks: list[str] = []
    for i, hit in enumerate(result.hits, start=1):
        if hit.source_id not in seen_sources:
            seen_sources.add(hit.source_id)
            citations.append(
                CitationOut(
                    source_id=hit.source_id,
                    title=hit.title,
                    url=hit.url,
                    excerpt=hit.excerpt,
                )
            )
        context_blocks.append(
            f"[{i}] title={hit.title}\nurl={hit.url or ''}\nsource_id={hit.source_id}\n{hit.excerpt}"
        )
    lang = "Chinese" if (output_language or "zh").startswith("zh") else "English"
    if not context_blocks:
        answer = (
            "知识库中暂无与该问题相关的素材。"
            if lang == "Chinese"
            else "No relevant material found in the knowledge base."
        )
        msg = Message(
            id=new_id("msg"),
            notebook_id=notebook_id,
            role="assistant",
            content=answer,
            citations_json=dumps([]),
        )
        db.add(
            Message(
                id=new_id("msg"),
                notebook_id=notebook_id,
                role="user",
                content=question,
                citations_json="[]",
            )
        )
        db.add(msg)
        db.commit()
        return AskResult(answer=answer, citations=[], message_id=msg.id)

    system = (
        "You answer questions using only the provided source excerpts. "
        f"Respond in {lang}. Cite sources inline like [1], [2] matching the excerpt numbers. "
        "If the sources are insufficient, say so clearly."
    )
    user = f"Question: {question}\n\nSources:\n" + "\n\n".join(context_blocks)
    answer = llm_svc.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=1200,
    )
    db.add(
        Message(
            id=new_id("msg"),
            notebook_id=notebook_id,
            role="user",
            content=question,
            citations_json="[]",
        )
    )
    msg = Message(
        id=new_id("msg"),
        notebook_id=notebook_id,
        role="assistant",
        content=answer,
        citations_json=dumps([c.model_dump() for c in citations]),
    )
    db.add(msg)
    brief_id = None
    if save_brief:
        # mark previous briefs not current
        db.query(Brief).filter(Brief.notebook_id == notebook_id, Brief.is_current == 1).update(
            {"is_current": 0}
        )
        brief = Brief(
            id=new_id("brief"),
            notebook_id=notebook_id,
            content_md=answer,
            citations_json=dumps([c.model_dump() for c in citations]),
            is_current=1,
        )
        db.add(brief)
        brief_id = brief.id
    db.commit()
    return AskResult(
        answer=answer,
        citations=citations,
        message_id=msg.id,
        brief_id=brief_id,
    )
