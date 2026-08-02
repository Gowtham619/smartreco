from typing import Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    db: Any  # SQLAlchemy Session for this run, injected by recommendation_service
    user_id: int
    interest_profile: dict[str, Any]
    query_text: str
    category_filter: Optional[str]
    candidates: list[dict[str, Any]]
    retry_count: int
    needs_retry: bool
    narrative: str
    picks: list[dict[str, Any]]
    trigger_reason: str
