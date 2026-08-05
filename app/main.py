import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import admin, auth, events, pages, recommendations
from app.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if os.getenv("AUTO_SEED", "false").lower() == "true":
        # Hosts with ephemeral disks (e.g. Render's free tier) lose SQLite/Chroma
        # data on redeploy or spin-down; reseeding is idempotent and cheap, so we
        # self-heal on every boot instead of shipping a demo with an empty catalog.
        from app.seed import seed

        seed()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="SmartReco", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(events.router)
app.include_router(recommendations.router)
