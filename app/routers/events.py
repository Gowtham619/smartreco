import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import EventBatchIn
from app.services import event_service, recommendation_service

router = APIRouter(prefix="/api", tags=["events"])
logger = logging.getLogger("smartreco.events")


@router.post("/events/batch", status_code=202)
async def ingest_events(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    # sendBeacon delivers a Blob (often as text/plain); parse the raw body
    # ourselves instead of relying on FastAPI's content-type-bound JSON body.
    raw = await request.body()
    if not raw:
        return Response(status_code=202)
    try:
        payload = EventBatchIn.model_validate(json.loads(raw))
    except Exception:
        logger.warning("Discarding malformed event batch", exc_info=True)
        return Response(status_code=202)

    if not user:
        # Anonymous browsing: nothing to attribute the events to, no-op.
        return Response(status_code=202)

    inserted = event_service.insert_events(db, user.id, payload.events)
    if inserted:
        background_tasks.add_task(recommendation_service.maybe_trigger_regeneration, user.id)
    return Response(status_code=202)
