from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC now — datetime.utcnow() is deprecated, but our DateTime
    columns and template formatting assume naive UTC throughout, so we keep
    that contract instead of migrating to timezone-aware columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
