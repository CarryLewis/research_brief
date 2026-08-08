"""Chunk indexing for lexical retrieval."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db import Chunk, SourceDoc
from ..utils import chunk_text, new_id, tokenize


def index_source(db: Session, source: SourceDoc) -> int:
    """Replace chunks for a source. Returns number of chunks written."""
    db.query(Chunk).filter(Chunk.doc_id == source.id).delete()
    text = (source.raw_text or "").strip()
    if not text or source.status == "failed":
        db.commit()
        return 0
    parts = chunk_text(text)
    count = 0
    for i, part in enumerate(parts):
        tokens = " ".join(tokenize(part))
        db.add(
            Chunk(
                id=new_id("chk"),
                notebook_id=source.notebook_id,
                doc_id=source.id,
                chunk_index=i,
                text=part,
                tokens=tokens,
            )
        )
        count += 1
    db.commit()
    return count


def index_sources(db: Session, sources: list[SourceDoc]) -> int:
    total = 0
    for src in sources:
        total += index_source(db, src)
    return total
