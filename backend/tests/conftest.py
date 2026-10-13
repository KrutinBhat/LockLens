from __future__ import annotations

import os
import time

import pytest

# Ensure default sandbox URLs before app imports (tests may override via env).
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://locklens:locklens_dev_pw@127.0.0.1:5432/locklens_test")
os.environ.setdefault("LAB_DATABASE_URL", "postgresql://locklens_lab:locklens_lab_pw@127.0.0.1:5432/locklens_lab_test")

import psycopg  # noqa: E402
from psycopg.conninfo import conninfo_to_dict, make_conninfo  # noqa: E402


def _ensure_db(name: str) -> None:
    # Derive the administration connection from DATABASE_URL so local Docker,
    # CI services, and explicitly configured test databases agree on host/port.
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    params = conninfo_to_dict(url)
    params["dbname"] = "postgres"
    conn = psycopg.connect(make_conninfo(**params), autocommit=True)
    exists = conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone()
    if not exists:
        conn.execute(f'CREATE DATABASE "{name}"')
    conn.close()


@pytest.fixture(scope="session", autouse=True)
def databases():
    _ensure_db("locklens_test")
    _ensure_db("locklens_lab_test")
    yield


@pytest.fixture()
def db_session(databases):
    from sqlalchemy import select
    from app.db import Base, SessionLocal, engine
    from app import models
    # wait for background runs/comparisons from earlier tests before resetting
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        db = SessionLocal()
        try:
            active = db.scalar(select(models.ExperimentRun).where(
                models.ExperimentRun.status.in_(["queued", "running", "paused"])).limit(1))
        except Exception:
            active = None
        finally:
            db.close()
        if active is None:
            break
        time.sleep(0.5)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def wait_run(client, run_id: int, timeout: float = 60.0, headers: dict | None = None) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/runs/{run_id}", headers=headers or {})
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] not in ("queued", "running", "paused"):
            return body
        time.sleep(0.3)
    raise TimeoutError(f"run {run_id} did not finish in {timeout}s")


def auth_headers(client, email: str = "a@b.c", password: str = "password123") -> dict:
    r = client.post("/api/auth/register",
                    json={"email": email, "display_name": email.split("@")[0], "password": password})
    assert r.status_code in (201, 409), r.text
    if r.status_code == 409:
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
