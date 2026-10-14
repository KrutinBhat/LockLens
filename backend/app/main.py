"""LockLens API application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, update

from .db import Base, SessionLocal, engine
from .config import settings
from . import models  # noqa: F401
from .lab.library import LIBRARY
from .routers import auth, comparisons, export, labinfo, runs, scenarios

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("locklens")


def seed_library() -> None:
    """Idempotently insert built-in scenario templates (is_template, project_id NULL)."""
    db = SessionLocal()
    try:
        for entry in LIBRARY:
            existing = db.scalar(select(models.Scenario).where(
                models.Scenario.is_template.is_(True), models.Scenario.key == entry["key"]))
            if existing:
                continue
            s = models.Scenario(project_id=None, is_template=True, key=entry["key"],
                                name=entry["name"], category=entry["category"],
                                description=entry["description"])
            db.add(s)
            db.flush()
            db.add(models.ScenarioVersion(scenario_id=s.id, version=1,
                                          definition=entry["definition"],
                                          change_note="library seed"))
        db.commit()
    finally:
        db.close()


def recover_interrupted_runs() -> None:
    """Close runs that cannot survive an API-process restart.

    Run coordination is intentionally in-process. A worker lost during a
    deployment must not remain displayed as live forever.
    """
    db = SessionLocal()
    try:
        db.execute(
            update(models.ExperimentRun)
            .where(models.ExperimentRun.status.in_(("queued", "running", "paused")))
            .values(status="failed", error="interrupted by API restart")
        )
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Alembic is canonical in production. create_all remains a convenience for
    # local development only; it must not silently bypass production migrations.
    if settings.environment.lower() != "production":
        Base.metadata.create_all(engine)
    if settings.environment.lower() == "production" and settings.jwt_secret == "dev-only-insecure-secret-change-me":
        raise RuntimeError("JWT_SECRET must be set to a non-default value in production")
    if settings.environment.lower() == "production" and not settings.cors_origins:
        raise RuntimeError("CORS_ORIGINS must list the production frontend origin")
    recover_interrupted_runs()
    seed_library()
    yield


app = FastAPI(title="LockLens API", version="0.1.0", lifespan=lifespan,
              description="Transaction Intelligence & Concurrency Experiment Platform")

app.add_middleware(
    CORSMiddleware,
    # Credentialed CORS cannot safely use a wildcard origin. Local Vite is the
    # development default; production must explicitly set CORS_ORIGINS.
    allow_origins=list(settings.cors_origins) or ["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error", "code": "internal"})


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/api/ready", tags=["meta"])
def readiness():
    from sqlalchemy import text
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        import psycopg
        from .config import settings
        with psycopg.connect(settings.lab_database_url, autocommit=True) as c:
            c.execute("SELECT 1")
        return {"metadata_db": "ok", "lab_db": "ok"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc), "code": "not_ready"})


app.include_router(auth.router)
app.include_router(scenarios.router)
app.include_router(runs.router)
app.include_router(comparisons.router)
app.include_router(export.router)
app.include_router(labinfo.router)
