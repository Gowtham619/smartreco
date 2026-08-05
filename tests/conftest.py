"""Test env vars must be set before any `app.*` module is imported, since
app/config.py builds its Settings() singleton at import time. This keeps
tests on an isolated SQLite file + Qdrant local-mode dir and never touches the
real Mesh account (LLM/embedding calls are monkeypatched per-test instead)."""

import os
import tempfile

_TEST_DIR = tempfile.mkdtemp(prefix="smartreco-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/test.db"
os.environ["QDRANT_LOCAL_PATH"] = f"{_TEST_DIR}/qdrant"
os.environ["MESH_API_KEY"] = "test-key-not-real"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_EMAIL"] = "admin@test.local"
os.environ["ADMIN_PASSWORD"] = "admin-pass-123"
os.environ["RECOMMENDATION_EVENT_THRESHOLD"] = "5"
os.environ["RECOMMENDATION_FIRST_EVENT_THRESHOLD"] = "3"
os.environ["RECOMMENDATION_COOLDOWN_MINUTES"] = "5"

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.database import Base, SessionLocal, engine, init_db
from app.main import app
from app.models import User, UserRole

init_db()


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _create_user(db, email, password, role):
    user = User(email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def regular_user(db_session):
    return _create_user(db_session, "user@test.local", "password123", UserRole.user)


@pytest.fixture()
def admin_user(db_session):
    return _create_user(db_session, "admin2@test.local", "password123", UserRole.admin)


@pytest.fixture()
def logged_in_client(client, regular_user):
    resp = client.post("/login", data={"email": regular_user.email, "password": "password123"})
    assert resp.status_code in (200, 303)
    return client


@pytest.fixture()
def admin_client(client, admin_user):
    resp = client.post("/login", data={"email": admin_user.email, "password": "password123"})
    assert resp.status_code in (200, 303)
    return client
