import pytest

from app.lab import sqlguard


def test_allows_single_select():
    assert sqlguard.validate_step_sql("SELECT * FROM lab.accounts WHERE id=1") \
        == "SELECT * FROM lab.accounts WHERE id=1"


def test_rejects_multi_statement():
    with pytest.raises(sqlguard.SqlRejected):
        sqlguard.validate_step_sql("SELECT 1; DROP TABLE lab.accounts")


def test_rejects_ddl_in_steps():
    with pytest.raises(sqlguard.SqlRejected):
        sqlguard.validate_step_sql("CREATE TABLE lab.x (id int)")


def test_rejects_dangerous_functions():
    for sql in ["SELECT pg_terminate_backend(1)", "SELECT pg_read_file('/etc/passwd')",
                "COPY lab.accounts TO '/tmp/x'", "SELECT dblink('x','y')"]:
        with pytest.raises(sqlguard.SqlRejected):
            sqlguard.validate_step_sql(sql)


def test_semicolon_inside_string_ok():
    stmt = sqlguard.validate_step_sql("INSERT INTO lab.t VALUES ('a;b')")
    assert "a;b" in stmt


def test_seed_allows_create_and_insert():
    stmts = sqlguard.validate_seed_sql(
        "CREATE TABLE lab.t (id int); INSERT INTO lab.t VALUES (1);")
    assert len(stmts) == 2


def test_table_extraction_and_write_detection():
    assert sqlguard.referenced_tables("UPDATE lab.accounts SET x=1") == {"accounts"}
    assert sqlguard.referenced_tables("SELECT * FROM lab.a JOIN lab.b ON a.id=b.id") == {"a", "b"}
    assert sqlguard.is_write("UPDATE lab.t SET x=1")
    assert not sqlguard.is_write("SELECT 1")


def test_split_statements_respects_dollar_quotes():
    stmts = sqlguard.split_statements("SELECT $$a;b$$; SELECT 2")
    assert len(stmts) == 2
