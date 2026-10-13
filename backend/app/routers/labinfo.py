"""Lab database introspection routes: schema, constraints, EXPLAIN, version metadata."""
from __future__ import annotations

import re

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..deps import current_user
from ..lab import sqlguard
from ..models import User

router = APIRouter(prefix="/api/lab", tags=["lab"])


def _lab_conn():
    return psycopg.connect(settings.lab_database_url, autocommit=True)


@router.get("/info")
def lab_info(user: User = Depends(current_user)):
    with _lab_conn() as conn:
        version = conn.execute("SELECT version()").fetchone()[0]
        settings_rows = conn.execute(
            "SELECT name, setting FROM pg_settings WHERE name IN "
            "('max_connections','deadlock_timeout','statement_timeout','lock_timeout','transaction_isolation')"
        ).fetchall()
        dbname = conn.execute("SELECT current_database()").fetchone()[0]
    return {"version": version, "database": dbname, "settings": dict(settings_rows)}


@router.get("/schema")
def lab_schema(user: User = Depends(current_user)):
    with _lab_conn() as conn:
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'lab' ORDER BY tablename").fetchall()
        out = []
        for (t,) in tables:
            cols = conn.execute(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema='lab' AND table_name=%s ORDER BY ordinal_position", (t,)).fetchall()
            cons = conn.execute(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = %s::regclass", (f"lab.{t}",)).fetchall()
            out.append({"table": t,
                        "columns": [{"name": c[0], "type": c[1], "nullable": c[2] == "YES"} for c in cols],
                        "constraints": [{"name": c[0], "definition": c[1]} for c in cons]})
    return {"tables": out}


_EXPLAIN_RE = re.compile(r"^\s*explain\b", re.IGNORECASE)


@router.post("/explain")
def lab_explain(body: dict, user: User = Depends(current_user)):
    sql = (body.get("sql") or "").strip()
    if not sql:
        raise HTTPException(status_code=422, detail="sql is required")
    inner = _EXPLAIN_RE.sub("", sql, count=1)
    validated = sqlguard.validate_step_sql(inner)
    with _lab_conn() as conn:
        conn.execute(f"SET statement_timeout = {int(settings.statement_timeout_ms)}")
        rows = conn.execute(f"EXPLAIN (COSTS FALSE) {validated}").fetchall()
    return {"plan": [r[0] for r in rows]}
