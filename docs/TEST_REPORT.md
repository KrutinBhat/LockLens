# Test report — 2026-10-13

## Executed in this workspace

- `cmd /c npm ci` in `frontend/`: command returned without an npm diagnostic, but the resulting TypeScript package directory was incomplete and `tsc` was unavailable.
- `cmd /c npm run build` in `frontend/`: **blocked** — `tsc` not recognized due to the incomplete local dependency installation.

## Not executable in this workspace

- Python and Docker executables are absent, so backend tests, Alembic migration checks, Docker Compose validation, and browser E2E could not be run.
- No PostgreSQL service was available for real-concurrency verification.

## Required verification commands

```powershell
docker compose up --build
cd backend; python -m pytest tests/ -q
cd ../frontend; npm ci; npm run build
npx playwright test
```

Do not interpret the unexecuted checks as passing. The GitHub Actions workflow is the recommended clean Linux verification environment after publishing.
