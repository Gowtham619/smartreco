import logging
from datetime import datetime, time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.models import Event, Product, User
from app.services import email_service, recommendation_service
from app.utils import utcnow

logger = logging.getLogger("smartreco.scheduler")

_scheduler: BackgroundScheduler | None = None


def _refresh_job():
    count = recommendation_service.refresh_stale_recommendations()
    logger.info("Scheduled refresh: regenerated recommendations for %d user(s)", count)


def _daily_digest_job():
    db = SessionLocal()
    try:
        today_start = datetime.combine(utcnow().date(), time.min)
        active_user_ids = {
            row[0]
            for row in db.query(Event.user_id).filter(Event.created_at >= today_start).distinct().all()
        }
        sent = 0
        for user_id in active_user_ids:
            user = db.get(User, user_id)
            if not user:
                continue
            rec = recommendation_service.ensure_recommendation(db, user_id)
            if not rec:
                continue
            product_ids = [i.product_id for i in rec.items]
            products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
            items = [
                {"title": products[i.product_id].title, "price": float(products[i.product_id].price), "reason": i.reason}
                for i in rec.items
                if i.product_id in products
            ]
            email_service.send_digest(user.email, rec.narrative, items)
            sent += 1
        logger.info("Daily digest: sent %d email(s)", sent)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _refresh_job,
        trigger=IntervalTrigger(minutes=settings.scheduler_refresh_minutes),
        id="refresh_stale_recommendations",
        replace_existing=True,
    )
    scheduler.add_job(
        _daily_digest_job,
        trigger=CronTrigger(hour=settings.digest_hour, minute=settings.digest_minute),
        id="daily_digest",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Scheduler started: refresh every %sm, daily digest at %02d:%02d UTC",
        settings.scheduler_refresh_minutes,
        settings.digest_hour,
        settings.digest_minute,
    )
    return scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
