"""Built-in scenario library: classic concurrency anomalies with deterministic
checkpoint schedules. Each definition is self-contained (seed, transactions,
invariants, final-state probe)."""
from __future__ import annotations

ACCOUNTS_SEED = [
    'CREATE TABLE lab.accounts (id int PRIMARY KEY, owner text NOT NULL, balance numeric NOT NULL CHECK (balance >= 0))',
    "INSERT INTO lab.accounts VALUES (1, 'alice', 100), (2, 'bob', 100)",
]

LIBRARY: list[dict] = [
    {
        "key": "lost_update",
        "name": "Lost Update — concurrent balance withdrawal",
        "category": "lost_update",
        "description": "T1 and T2 both read balance=100, each subtracts 20 in application logic and "
                       "writes back the computed value. Under READ COMMITTED the second commit "
                       "overwrites the first: final balance is 80 instead of 60. The counterfactual "
                       "serial replays prove no serial order yields 80.",
        "definition": {
            "seed_sql": ACCOUNTS_SEED,
            "transactions": [
                {"name": "T1", "isolation": "READ COMMITTED", "steps": [
                    {"kind": "sql", "sql": "SELECT balance FROM lab.accounts WHERE id = 1", "save_as": "bal"},
                    {"kind": "checkpoint", "name": "both_read"},
                    {"kind": "sql", "sql": "UPDATE lab.accounts SET balance = {{bal}} - 20 WHERE id = 1"},
                    {"kind": "commit"},
                ]},
                {"name": "T2", "isolation": "READ COMMITTED", "steps": [
                    {"kind": "sql", "sql": "SELECT balance FROM lab.accounts WHERE id = 1", "save_as": "bal"},
                    {"kind": "checkpoint", "name": "both_read"},
                    {"kind": "sql", "sql": "UPDATE lab.accounts SET balance = {{bal}} - 20 WHERE id = 1"},
                    {"kind": "commit"},
                ]},
            ],
            "invariants": [
                {"name": "balance_reflects_both_withdrawals",
                 "sql": "SELECT balance FROM lab.accounts WHERE id = 1", "expect": "60"},
            ],
            "final_state_sql": "SELECT id, balance FROM lab.accounts ORDER BY id",
        },
    },
    {
        "key": "non_repeatable_read",
        "name": "Non-Repeatable Read — price changes mid-transaction",
        "category": "non_repeatable_read",
        "description": "T1 reads a product price twice; T2 updates and commits in between. Under "
                       "READ COMMITTED the second read sees the new price — a confirmed "
                       "non-repeatable read.",
        "definition": {
            "seed_sql": [
                "CREATE TABLE lab.products (id int PRIMARY KEY, name text NOT NULL, price numeric NOT NULL)",
                "INSERT INTO lab.products VALUES (1, 'widget', 50)",
            ],
            "transactions": [
                {"name": "T1", "isolation": "READ COMMITTED", "steps": [
                    {"kind": "sql", "sql": "SELECT price FROM lab.products WHERE id = 1"},
                    {"kind": "checkpoint", "name": "t1_read"}, {"kind": "checkpoint", "name": "t2_committed"},
                    {"kind": "sql", "sql": "SELECT price FROM lab.products WHERE id = 1"},
                    {"kind": "commit"},
                ]},
                {"name": "T2", "isolation": "READ COMMITTED", "steps": [
                    {"kind": "checkpoint", "name": "t1_read"}, {"kind": "sql", "sql": "UPDATE lab.products SET price = 75 WHERE id = 1"},
                    {"kind": "commit"},
                    {"kind": "checkpoint", "name": "t2_committed"},
                ]},
            ],
            "invariants": [],
            "final_state_sql": "SELECT id, price FROM lab.products ORDER BY id",
        },
    },
    {
        "key": "write_skew",
        "name": "Write Skew — on-call invariant broken",
        "category": "write_skew",
        "description": "Invariant: at least one doctor stays on call. T1 and T2 each check the "
                       "count of on-call doctors (2), then take THEMSELVES off call. Under "
                       "REPEATABLE READ (snapshot isolation) both checks pass, both commits "
                       "succeed, and the invariant is violated — classic write skew.",
        "definition": {
            "seed_sql": [
                "CREATE TABLE lab.doctors (id int PRIMARY KEY, name text NOT NULL, on_call boolean NOT NULL)",
                "INSERT INTO lab.doctors VALUES (1, 'alice', true), (2, 'bob', true)",
            ],
            "transactions": [
                {"name": "T1", "isolation": "REPEATABLE READ", "steps": [
                    {"kind": "sql", "sql": "SELECT count(*) AS on_call FROM lab.doctors WHERE on_call"},
                    {"kind": "checkpoint", "name": "both_checked"},
                    {"kind": "sql", "sql": "UPDATE lab.doctors SET on_call = false WHERE id = 1"},
                    {"kind": "commit"},
                ]},
                {"name": "T2", "isolation": "REPEATABLE READ", "steps": [
                    {"kind": "sql", "sql": "SELECT count(*) AS on_call FROM lab.doctors WHERE on_call"},
                    {"kind": "checkpoint", "name": "both_checked"},
                    {"kind": "sql", "sql": "UPDATE lab.doctors SET on_call = false WHERE id = 2"},
                    {"kind": "commit"},
                ]},
            ],
            "invariants": [
                {"name": "at_least_one_on_call",
                 "sql": "SELECT count(*) FROM lab.doctors WHERE on_call = false", "expect": "0"},
            ],
            "final_state_sql": "SELECT id, name, on_call FROM lab.doctors ORDER BY id",
        },
    },
    {
        "key": "deadlock",
        "name": "Deadlock — opposite lock order",
        "category": "deadlock",
        "description": "T1 locks account 1 then account 2; T2 locks account 2 then account 1. "
                       "PostgreSQL's deadlock detector aborts one transaction with SQLSTATE 40P01. "
                       "The wait-for graph shows the cycle.",
        "definition": {
            "seed_sql": ACCOUNTS_SEED,
            "transactions": [
                {"name": "T1", "isolation": "READ COMMITTED", "steps": [
                    {"kind": "sql", "sql": "UPDATE lab.accounts SET balance = balance - 10 WHERE id = 1"},
                    {"kind": "checkpoint", "name": "first_locks"},
                    {"kind": "sql", "sql": "UPDATE lab.accounts SET balance = balance - 10 WHERE id = 2"},
                    {"kind": "commit"},
                ]},
                {"name": "T2", "isolation": "READ COMMITTED", "steps": [
                    {"kind": "sql", "sql": "UPDATE lab.accounts SET balance = balance - 10 WHERE id = 2"},
                    {"kind": "checkpoint", "name": "first_locks"},
                    {"kind": "sql", "sql": "UPDATE lab.accounts SET balance = balance - 10 WHERE id = 1"},
                    {"kind": "commit"},
                ]},
            ],
            "invariants": [
                {"name": "total_balance_preserved",
                 "sql": "SELECT CASE WHEN sum(balance) IN (200, 180, 190) THEN 'ok' ELSE 'bad:' || sum(balance) END FROM lab.accounts",
                 "expect": "ok"},
            ],
            "final_state_sql": "SELECT id, balance FROM lab.accounts ORDER BY id",
        },
    },
    {
        "key": "serialization_failure",
        "name": "Serialization Failure — SERIALIZABLE rejects write skew",
        "category": "serialization_failure",
        "description": "The write-skew schedule under SERIALIZABLE: PostgreSQL's SSI detects the "
                       "dangerous rw-antidependency cycle and aborts one transaction with "
                       "SQLSTATE 40001, preserving the on-call invariant.",
        "definition": {
            "seed_sql": [
                "CREATE TABLE lab.doctors (id int PRIMARY KEY, name text NOT NULL, on_call boolean NOT NULL)",
                "INSERT INTO lab.doctors VALUES (1, 'alice', true), (2, 'bob', true)",
            ],
            "transactions": [
                {"name": "T1", "isolation": "SERIALIZABLE", "steps": [
                    {"kind": "sql", "sql": "SELECT count(*) AS on_call FROM lab.doctors WHERE on_call"},
                    {"kind": "checkpoint", "name": "both_checked"},
                    {"kind": "sql", "sql": "UPDATE lab.doctors SET on_call = false WHERE id = 1"},
                    {"kind": "checkpoint", "name": "both_wrote"},
                    {"kind": "commit"},
                ]},
                {"name": "T2", "isolation": "SERIALIZABLE", "steps": [
                    {"kind": "sql", "sql": "SELECT count(*) AS on_call FROM lab.doctors WHERE on_call"},
                    {"kind": "checkpoint", "name": "both_checked"},
                    {"kind": "sql", "sql": "UPDATE lab.doctors SET on_call = false WHERE id = 2"},
                    {"kind": "checkpoint", "name": "both_wrote"},
                    {"kind": "commit"},
                ]},
            ],
            "invariants": [
                {"name": "at_least_one_on_call",
                 "sql": "SELECT count(*) FROM lab.doctors WHERE on_call = false", "expect": "0"},
            ],
            "final_state_sql": "SELECT id, name, on_call FROM lab.doctors ORDER BY id",
        },
    },
    {
        "key": "controlled_race_counter",
        "name": "Atomic Increment vs Read-Modify-Write",
        "category": "lost_update",
        "description": "Baseline for the Repair Lab: 2 transactions each increment a counter via "
                       "read-modify-write. Then compare with the atomic UPDATE ... SET n = n + 1 "
                       "repair to see correctness and lock-wait differences.",
        "definition": {
            "seed_sql": [
                "CREATE TABLE lab.counters (id int PRIMARY KEY, n int NOT NULL)",
                "INSERT INTO lab.counters VALUES (1, 0)",
            ],
            "transactions": [
                {"name": "T1", "isolation": "READ COMMITTED", "steps": [
                    {"kind": "sql", "sql": "SELECT n FROM lab.counters WHERE id = 1", "save_as": "n"},
                    {"kind": "checkpoint", "name": "both_read"},
                    {"kind": "sql", "sql": "UPDATE lab.counters SET n = {{n}} + 1 WHERE id = 1"},
                    {"kind": "commit"},
                ]},
                {"name": "T2", "isolation": "READ COMMITTED", "steps": [
                    {"kind": "sql", "sql": "SELECT n FROM lab.counters WHERE id = 1", "save_as": "n"},
                    {"kind": "checkpoint", "name": "both_read"},
                    {"kind": "sql", "sql": "UPDATE lab.counters SET n = {{n}} + 1 WHERE id = 1"},
                    {"kind": "commit"},
                ]},
            ],
            "invariants": [
                {"name": "both_increments_applied",
                 "sql": "SELECT n FROM lab.counters WHERE id = 1", "expect": "2"},
            ],
            "final_state_sql": "SELECT id, n FROM lab.counters ORDER BY id",
        },
    },
]
