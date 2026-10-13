# Engineering audit — 2026-10-13

## Inventory

LockLens is a FastAPI + SQLAlchemy metadata API, a React/Vite user interface, and a PostgreSQL concurrency laboratory. The backend contains authenticated scenario, run, comparison, export, and lab-introspection routers. The lab engine creates one psycopg connection per transaction and records events, sampled locks, metrics, and detector findings. The frontend supplies dashboard, scenario editing, run timeline, history, comparison, and lab pages.

## Architecture and data

- `backend/app/models.py` holds users, projects, immutable scenario versions, experiment runs, session/event/lock evidence, metrics, comparisons, and audit events.
- `backend/alembic/versions/cdc834130b17_initial_schema.py` is the sole metadata migration. `db/init/01_lab.sql` provisions the separate lab database and least-privilege role for a fresh Docker volume.
- Scenario fixtures in `backend/app/lab/library.py` are generated/reproducible experiment definitions, not a third-party tabular dataset. No CSV, notebook, ML model, or public dataset is present.
- `sqlguard.py` validates one allowed step statement; the dedicated lab database and limited role are the real safety boundary.

## Baseline findings and repairs

1. The test fixture forced port 55432 even when CI exposes PostgreSQL at 5432. It now derives its administration connection from `DATABASE_URL`.
2. Local defaults conflicted with Docker Compose's published 5432 port and omitted database passwords. Defaults and `.env.example` now match Compose.
3. Credentialed CORS used a wildcard. Production now requires explicit `CORS_ORIGINS`; development is limited to local Vite origins.
4. Runtime schema creation could hide a missed production migration. It is now development-only; the Docker entrypoint runs Alembic first.
5. The Docker API now binds Render's `PORT`; `render.yaml` and deployment instructions are included.
6. This directory was not a Git repository at audit time. Git initialization is part of delivery preparation; no remote or deployment credentials were available.

## Existing verification assets

- Backend: SQL guard, analyzers, API, and real-PostgreSQL engine integration tests.
- Frontend: TypeScript/Vite build plus a Playwright critical account → scenario → evidence → export flow.
- CI: PostgreSQL 17 service and frontend build/e2e workflow.

## Remaining risks

The lab reset drops tables in its dedicated `lab` schema, so deployment must use a genuinely isolated lab endpoint. Run coordination is in process and must remain single-instance. The Render deployment cannot be performed or declared live without a GitHub repository and authenticated Render account.
