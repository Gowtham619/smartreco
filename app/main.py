import logging
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
