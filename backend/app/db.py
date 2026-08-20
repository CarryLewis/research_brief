from datetime import datetime, timezone

from sqlalchemy import DateTime, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ThinkingSyncState(Base):
    """Notion Thinking page → Obsidian file sync index (source_id is identity)."""

    __tablename__ = "thinking_sync_state"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    vault_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    notion_last_edited: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # active | archived
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


_settings = get_settings()
engine = create_engine(
    f"sqlite:///{_settings.db_path}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
