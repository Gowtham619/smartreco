from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Event, EventType
from app.schemas import EventIn

VALID_EVENT_TYPES = {e.value for e in EventType}


def insert_events(db: Session, user_id: int, events: list[EventIn]) -> int:
    rows = []
    for e in events:
        if e.event_type not in VALID_EVENT_TYPES:
            continue
        rows.append(
            Event(
                user_id=user_id,
                event_type=e.event_type,
                product_id=e.product_id,
                query=(e.query or "")[:255] or None,
                meta=e.meta,
                duration_ms=e.duration_ms,
            )
        )
    if not rows:
        return 0
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def get_recent_events(db: Session, user_id: int, limit: int = 50) -> list[Event]:
    return (
        db.query(Event)
        .filter(Event.user_id == user_id)
        .order_by(Event.created_at.desc())
        .limit(limit)
        .all()
    )


def count_events_since(db: Session, user_id: int, since: datetime | None) -> int:
    q = db.query(func.count(Event.id)).filter(Event.user_id == user_id)
    if since:
        q = q.filter(Event.created_at > since)
    return q.scalar() or 0


def total_event_count(db: Session, user_id: int) -> int:
    return db.query(func.count(Event.id)).filter(Event.user_id == user_id).scalar() or 0
