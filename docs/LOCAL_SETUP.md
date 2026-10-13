# Local setup

## Prerequisites

- Docker Desktop (recommended), or PostgreSQL 17+, Python 3.12+, and Node 20+.

## Docker

```powershell
Copy-Item .env.example .env
# Replace JWT_SECRET in .env with a random value before sharing the environment.
docker compose up --build
```

The frontend is at `http://localhost:3000`; the API docs are at `http://localhost:8000/docs`.
The first database start initializes `locklens` and `locklens_lab`. PostgreSQL init scripts only run when the `pgdata` volume is new. To intentionally recreate local data, run `docker compose down -v` and then `docker compose up --build`.

## Native development

Set `DATABASE_URL` and `LAB_DATABASE_URL` to separate PostgreSQL databases, then:

```powershell
cd backend
python -m pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload

cd ../frontend
npm ci
npm run dev
```

Do not point `LAB_DATABASE_URL` at the metadata database: runs reset the `lab` schema.

## Checks

```powershell
cd backend; python -m pytest tests/ -q
cd ../frontend; npm run build
```

Real concurrency tests need PostgreSQL reachable through the two configured URLs. CI uses port 5432; no test code hardcodes a conflicting port.
