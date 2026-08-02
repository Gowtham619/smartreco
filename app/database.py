from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent

database_url = settings.database_url
if database_url.startswith("sqlite:///./"):
    abs_path = BASE_DIR / database_url.removeprefix("sqlite:///./")
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{abs_path}"

engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
