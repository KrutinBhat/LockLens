"""SQL safety guard for experiment steps.

Defense-in-depth note: the primary isolation boundary is that experiment SQL
only ever executes against the dedicated lab database with bounded timeouts.
This guard additionally rejects multi-statement payloads, DDL/DCL in
transaction steps, and dangerous functions. It is NOT a general SQL sandbox
and is documented as such.
"""
from __future__ import annotations

import re

# Statements allowed inside transaction steps
_STEP_VERBS = {"select", "insert", "update", "delete", "values"}
# Statements allowed in seed/setup SQL (runs as orchestrator, still lab DB only)
_SEED_VERBS = _STEP_VERBS | {"create", "drop", "alter", "truncate"}

_DENY_PATTERNS = [
    r"\bpg_terminate_backend\b",
    r"\bpg_cancel_backend\b",
    r"\bpg_read_file\b",
    r"\bpg_write_file\b",
    r"\bcopy\b",
    r"\bdo\b\s*(\$\$|\")",
    r"\bset\s+(role|session_authorization)\b",
    r"\bsecurity\s+definer\b",
    r"\bgrant\b",
    r"\brevoke\b",
    r"\bcreate\s+(extension|role|user|database)\b",
    r"\bdrop\s+(role|user|database)\b",
    r"\balter\s+(system|role|user|database)\b",
    r"\blisten\b",
    r"\bnotify\b",
    r"\bdblink\b",
    r"\blo_import\b",
    r"\binto\s+outfile\b",
]
_DENY_RE = re.compile("|".join(f"(?:{p})" for p in _DENY_PATTERNS), re.IGNORECASE | re.DOTALL)


class SqlRejected(ValueError):
    pass


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql


def split_statements(sql: str) -> list[str]:
    """Split on top-level semicolons, respecting single/double quotes and dollar quotes."""
    parts: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    in_s = in_d = False
    dollar_tag: str | None = None
    while i < n:
        ch = sql[i]
        if dollar_tag is not None:
            if sql.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
                continue
            buf.append(ch)
            i += 1
            continue
        if in_s:
            buf.append(ch)
            if ch == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_s = False
            i += 1
            continue
        if in_d:
            buf.append(ch)
            if ch == '"':
                in_d = False
            i += 1
            continue
        if ch == "'":
            in_s = True
            buf.append(ch)
        elif ch == '"':
            in_d = True
            buf.append(ch)
        elif ch == "$":
            m = re.match(r"\$[A-Za-z_]*\$", sql[i:])
            if m:
                dollar_tag = m.group(0)
                buf.append(dollar_tag)
                i += len(dollar_tag)
                continue
            buf.append(ch)
        elif ch == ";":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf)
    if tail.strip():
        parts.append(tail)
    return [p.strip() for p in parts if p.strip()]


def _first_verb(stmt: str) -> str:
    m = re.match(r"^\s*(?:\(\s*)*([a-zA-Z]+)", stmt)
    return m.group(1).lower() if m else ""


def validate_step_sql(sql: str, max_rows_hint: int = 0) -> str:
    """Validate one transaction-step statement. Returns normalized SQL or raises SqlRejected."""
    cleaned = _strip_comments(sql).strip()
    if not cleaned:
        raise SqlRejected("empty SQL")
    stmts = split_statements(cleaned)
    if len(stmts) != 1:
        raise SqlRejected("transaction steps must contain exactly one statement")
    stmt = stmts[0]
    if _DENY_RE.search(stmt):
        raise SqlRejected("statement contains a denied pattern")
    verb = _first_verb(stmt)
    if verb not in _STEP_VERBS:
        raise SqlRejected(f"only {sorted(_STEP_VERBS)} statements are allowed in transaction steps, got {verb!r}")
    return stmt


def validate_seed_sql(sql: str) -> list[str]:
    """Validate seed/setup SQL. Multiple statements allowed. Returns statement list."""
    cleaned = _strip_comments(sql)
    stmts = split_statements(cleaned)
    if not stmts:
        raise SqlRejected("seed SQL is empty")
    for stmt in stmts:
        if _DENY_RE.search(stmt):
            raise SqlRejected(f"seed statement contains a denied pattern: {stmt[:60]}")
        verb = _first_verb(stmt)
        if verb not in _SEED_VERBS:
            raise SqlRejected(f"seed statement verb {verb!r} not allowed")
    return stmts


# Simple table-reference extractor for table-level dependency edges.
_TABLE_RE = re.compile(
    r"\b(?:from|join|update|into)\s+([a-zA-Z_][\w.]*)", re.IGNORECASE
)
_WRITE_RE = re.compile(r"^\s*(?:insert|update|delete)\b", re.IGNORECASE)


def referenced_tables(sql: str) -> set[str]:
    return {t.split(".")[-1].lower() for t in _TABLE_RE.findall(sql)}


def is_write(sql: str) -> bool:
    return bool(_WRITE_RE.match(sql))
