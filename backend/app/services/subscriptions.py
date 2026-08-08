"""Subscription catalog: manage newsletter senders for inbound filtering."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db import Subscription, utcnow
from ..schemas import SubscriptionCreate, SubscriptionOut, SubscriptionUpdate
from ..utils import dumps, loads, new_id


def to_out(row: Subscription) -> SubscriptionOut:
    return SubscriptionOut(
        id=row.id,
        name=row.name,
        sender_pattern=row.sender_pattern,
        enabled=bool(row.enabled),
        tags=loads(row.tags_json, []) or [],
        notes=row.notes or "",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_subscriptions(db: Session, *, enabled_only: bool = False) -> list[SubscriptionOut]:
    q = db.query(Subscription).order_by(Subscription.name.asc())
    if enabled_only:
        q = q.filter(Subscription.enabled == 1)
    return [to_out(r) for r in q.all()]


def get_subscription(db: Session, sub_id: str) -> Subscription | None:
    return db.get(Subscription, sub_id)


def create_subscription(db: Session, payload: SubscriptionCreate) -> SubscriptionOut:
    pattern = (payload.sender_pattern or "").strip()
    if not pattern:
        raise ValueError("sender_pattern is required")
    name = (payload.name or "").strip() or pattern
    row = Subscription(
        id=new_id("sub"),
        name=name,
        sender_pattern=pattern,
        enabled=1 if payload.enabled else 0,
        tags_json=dumps(payload.tags or []),
        notes=payload.notes or "",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return to_out(row)


def update_subscription(
    db: Session, row: Subscription, payload: SubscriptionUpdate
) -> SubscriptionOut:
    if payload.name is not None:
        row.name = payload.name.strip() or row.name
    if payload.sender_pattern is not None:
        pat = payload.sender_pattern.strip()
        if not pat:
            raise ValueError("sender_pattern cannot be empty")
        row.sender_pattern = pat
    if payload.enabled is not None:
        row.enabled = 1 if payload.enabled else 0
    if payload.tags is not None:
        row.tags_json = dumps(payload.tags)
    if payload.notes is not None:
        row.notes = payload.notes
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return to_out(row)


def delete_subscription(db: Session, row: Subscription) -> None:
    db.delete(row)
    db.commit()


def match_sender(sender: str, pattern: str) -> bool:
    """Match From header against catalog pattern (*@domain or substring)."""
    sender_l = (sender or "").lower()
    pat = (pattern or "").lower().strip()
    if not pat:
        return False
    if pat.startswith("*@"):
        return sender_l.endswith(pat[1:]) or f"@{pat[2:]}" in sender_l
    return pat in sender_l


def find_matching_subscription(db: Session, sender: str) -> Subscription | None:
    rows = (
        db.query(Subscription)
        .filter(Subscription.enabled == 1)
        .order_by(Subscription.name.asc())
        .all()
    )
    for row in rows:
        if match_sender(sender, row.sender_pattern):
            return row
    return None
