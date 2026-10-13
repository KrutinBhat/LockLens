# Feature traceability

| Requirement | Implementation | Verification status |
| --- | --- | --- |
| Separate metadata and lab databases | `config.py`, `db.py`, `engine.py`, `db/init/01_lab.sql` | Implemented; needs real deployment credentials |
| Deterministic checkpoint schedules | `lab/engine.py` (`Checkpoint`, workers, event recorder) | Covered by backend integration tests; not rerun in this environment |
| Actual PostgreSQL transaction isolation | psycopg workers and library scenarios | Covered by integration tests; requires PostgreSQL |
| Evidence-backed findings | `lab/analyzers.py`, events, lock observations | Covered by analyzer/API tests; not rerun here |
| Counterfactual comparison | `routers/comparisons.py` | Implemented; single-run limitations are returned in verdict |
| Authentication and ownership checks | `security.py`, `deps.py`, routers | Covered by API tests; not rerun here |
| Production deployment | `backend/Dockerfile`, `render.yaml`, `docs/DEPLOYMENT.md` | Prepared, not deployed |
| GitHub CI | `.github/workflows/ci.yml` | Prepared; requires push to GitHub to execute |
