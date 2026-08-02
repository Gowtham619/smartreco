import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.agent.graph import build_graph
from app.config import settings
from app.database import SessionLocal
from app.models import Recommendation, RecommendationItem, RecommendationState, User
from app.services import event_service

logger = logging.getLogger("smartreco.recommendation_service")


def get_or_create_state(db: Session, user_id: int) -> RecommendationState:
    state = db.get(RecommendationState, user_id)
    if not state:
        state = RecommendationState(user_id=user_id, event_count_at_last_gen=0, generating=False)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def _threshold_for(state: RecommendationState) -> int:
    return (
        settings.recommendation_event_threshold
        if state.last_generated_at
        else settings.recommendation_first_event_threshold
    )


def _cooldown_active(state: RecommendationState) -> bool:
    if not state.last_generated_at:
        return False
    return datetime.utcnow() - state.last_generated_at < timedelta(minutes=settings.recommendation_cooldown_minutes)


def _run_generation(db: Session, user_id: int, trigger_reason: str) -> Recommendation:
    state = get_or_create_state(db, user_id)
    state.generating = True
    db.commit()
    try:
        graph = build_graph()
        result = graph.invoke({"db": db, "user_id": user_id, "trigger_reason": trigger_reason})
        narrative = result.get("narrative") or "Here's what SmartReco thinks fits where you're headed."
        picks = result.get("picks", [])

        rec = Recommendation(
            user_id=user_id,
            narrative=narrative,
            trigger_reason=trigger_reason,
            model_used=settings.mesh_chat_model,
        )
        db.add(rec)
        db.flush()
        for i, pick in enumerate(picks, start=1):
            db.add(
                RecommendationItem(
                    recommendation_id=rec.id,
                    product_id=pick["product_id"],
                    rank=i,
                    reason=pick.get("reason"),
                )
            )
        state.last_generated_at = datetime.utcnow()
        state.event_count_at_last_gen = event_service.total_event_count(db, user_id)
        state.generating = False
        db.commit()
        db.refresh(rec)
        logger.info("Generated recommendation %s for user %s (trigger=%s)", rec.id, user_id, trigger_reason)
        return rec
    except Exception:
        logger.error("Recommendation generation failed for user %s", user_id, exc_info=True)
        state.generating = False
        db.commit()
        raise


def get_latest(db: Session, user_id: int) -> Recommendation | None:
    return (
        db.query(Recommendation)
        .filter(Recommendation.user_id == user_id)
        .order_by(Recommendation.created_at.desc())
        .first()
    )


def ensure_recommendation(db: Session, user_id: int) -> Recommendation | None:
    rec = get_latest(db, user_id)
    if rec is None:
        try:
            rec = _run_generation(db, user_id, "first_visit")
        except Exception:
            return None
    return rec


def force_refresh(user_id: int) -> None:
    db = SessionLocal()
    try:
        _run_generation(db, user_id, "manual_refresh")
    finally:
        db.close()


def maybe_trigger_regeneration(user_id: int, reason: str = "activity_threshold") -> None:
    """Called from a FastAPI BackgroundTask after an event batch is ingested.

    Runs in its own DB session since the request-scoped session is closed by
    the time background tasks execute. Cheap checks (counts, timestamps) run
    first so the LLM only fires when a real behavioral trigger is met.
    """
    db = SessionLocal()
    try:
        state = get_or_create_state(db, user_id)
        if state.generating or _cooldown_active(state):
            return
        total_events = event_service.total_event_count(db, user_id)
        new_events = total_events - (state.event_count_at_last_gen or 0)
        if new_events < _threshold_for(state):
            return
        _run_generation(db, user_id, reason)
    finally:
        db.close()


def refresh_stale_recommendations() -> int:
    """Scheduler safety-net: catches users whose activity trickled in without
    crossing the real-time trigger in maybe_trigger_regeneration."""
    db = SessionLocal()
    refreshed = 0
    try:
        for user in db.query(User).all():
            state = get_or_create_state(db, user.id)
            if state.generating or _cooldown_active(state):
                continue
            total_events = event_service.total_event_count(db, user.id)
            new_events = total_events - (state.event_count_at_last_gen or 0)
            if total_events == 0 or new_events < _threshold_for(state):
                continue
            try:
                _run_generation(db, user.id, "scheduled_refresh")
                refreshed += 1
            except Exception:
                continue
        return refreshed
    finally:
        db.close()
