"""API-level tests: auth, authorization, scenario CRUD, run lifecycle, export."""
from __future__ import annotations

from tests.conftest import auth_headers, wait_run


def test_health_and_ready(client):
    assert client.get("/api/health").status_code == 200
    r = client.get("/api/ready")
    assert r.status_code == 200 and r.json()["lab_db"] == "ok"


def test_register_login_me(client):
    h = auth_headers(client, "u1@example.com")
    r = client.get("/api/auth/me", headers=h)
    assert r.status_code == 200 and r.json()["email"] == "u1@example.com"
    # wrong password rejected
    bad = client.post("/api/auth/login", json={"email": "u1@example.com", "password": "wrongpass1"})
    assert bad.status_code == 401


def test_unauthenticated_rejected(client):
    assert client.get("/api/scenarios").status_code == 401
    assert client.get("/api/runs").status_code == 401


def test_library_seeded_and_visible(client):
    h = auth_headers(client, "lib@example.com")
    r = client.get("/api/scenarios", headers=h)
    assert r.status_code == 200
    keys = {s["key"] for s in r.json()["items"]}
    assert {"lost_update", "write_skew", "deadlock", "serialization_failure"} <= keys


def test_run_lost_update_end_to_end(client):
    h = auth_headers(client, "run@example.com")
    scenarios = client.get("/api/scenarios?q=lost_update", headers=h).json()["items"]
    sc = next(s for s in scenarios if s["key"] == "lost_update")
    r = client.post("/api/runs", headers=h,
                    json={"scenario_version_id": sc["latest_version"]["id"]})
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    final = wait_run(client, run_id, headers=h)
    assert final["status"] == "anomaly_detected"
    assert final["metrics"]["invariant_violations"] == 1
    detail = client.get(f"/api/runs/{run_id}", headers=h).json()
    assert len(detail["events"]) > 0
    detectors = {f["detector"] for f in detail["analysis"]["findings"]}
    assert "invariant_violation" in detectors
    assert "non_serializable_outcome" in detectors
    # exports
    assert client.get(f"/api/export/runs/{run_id}.json", headers=h).status_code == 200
    assert client.get(f"/api/export/runs/{run_id}.csv", headers=h).status_code == 200
    html = client.get(f"/api/export/runs/{run_id}.html", headers=h)
    assert html.status_code == 200 and "LockLens Experiment Report" in html.text


def test_cross_user_access_denied(client):
    h1 = auth_headers(client, "owner@example.com")
    h2 = auth_headers(client, "intruder@example.com")
    # owner creates a private scenario
    body = {
        "key": "private_sc", "name": "Private", "category": "custom", "description": "",
        "definition": {
            "seed_sql": ["CREATE TABLE lab.t_priv (id int PRIMARY KEY)", "INSERT INTO lab.t_priv VALUES (1)"],
            "transactions": [{"name": "T1", "isolation": "READ COMMITTED",
                              "steps": [{"kind": "sql", "sql": "SELECT * FROM lab.t_priv"},
                                        {"kind": "commit"}]}],
            "invariants": [], "final_state_sql": "SELECT * FROM lab.t_priv",
        },
    }
    r = client.post("/api/scenarios", headers=h1, json=body)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    # intruder cannot see it
    assert client.get(f"/api/scenarios/{sid}", headers=h2).status_code == 404
    # intruder cannot run it
    vid = r.json()["latest_version"]["id"]
    assert client.post("/api/runs", headers=h2, json={"scenario_version_id": vid}).status_code == 404


def test_sql_validation_rejects_injection(client):
    h = auth_headers(client, "sec@example.com")
    body = {
        "key": "evil", "name": "Evil", "category": "custom", "description": "",
        "definition": {
            "seed_sql": ["CREATE TABLE lab.t_evil (id int PRIMARY KEY)"],
            "transactions": [{"name": "T1", "isolation": "READ COMMITTED",
                              "steps": [{"kind": "sql", "sql": "SELECT 1; DROP TABLE lab.t_evil"},
                                        {"kind": "commit"}]}],
            "invariants": [],
        },
    }
    r = client.post("/api/scenarios", headers=h, json=body)
    assert r.status_code == 422


def test_run_control_cancel(client):
    import time
    h = auth_headers(client, "ctl@example.com")
    scenarios = client.get("/api/scenarios?q=lost_update", headers=h).json()["items"]
    sc = next(s for s in scenarios if s["key"] == "lost_update")
    r = client.post("/api/runs", headers=h, json={"scenario_version_id": sc["latest_version"]["id"]})
    run_id = r.json()["id"]
    time.sleep(0.4)
    c = client.post(f"/api/runs/{run_id}/control", headers=h, json={"action": "cancel"})
    assert c.status_code in (200, 409)  # may have already finished
    final = wait_run(client, run_id, headers=h)
    assert final["status"] in ("cancelled", "anomaly_detected", "succeeded")


def test_comparison_repair_lab(client):
    h = auth_headers(client, "cmp@example.com")
    scenarios = client.get("/api/scenarios?q=counter", headers=h).json()["items"]
    sc = next(s for s in scenarios if s["key"] == "controlled_race_counter")
    r = client.post("/api/comparisons", headers=h, json={
        "name": "FOR UPDATE repair",
        "scenario_version_id": sc["latest_version"]["id"],
        "change": {"for_update": True},
    })
    assert r.status_code == 201, r.text
    comp_id = r.json()["id"]
    import time
    for _ in range(240):
        c = client.get(f"/api/comparisons/{comp_id}", headers=h).json()
        if c.get("baseline_run_id") is not None and c["verdict"].get("status") != "running":
            break
        time.sleep(0.5)
    assert c["baseline_run_id"] and c["candidate_run_id"]
    v = c["verdict"]
    # baseline loses an increment; candidate (SELECT FOR UPDATE) preserves it
    assert v["baseline"]["invariant_violations"] == 1
    assert v["candidate"]["invariant_violations"] == 0
    assert v["correctness_improved"] is True
    assert v["limitations"]


def test_lab_info_and_explain(client):
    h = auth_headers(client, "lab@example.com")
    info = client.get("/api/lab/info", headers=h)
    assert info.status_code == 200 and "PostgreSQL" in info.json()["version"]
    # seed something so a table exists for explain
    scenarios = client.get("/api/scenarios?q=lost_update", headers=h).json()["items"]
    sc = next(s for s in scenarios if s["key"] == "lost_update")
    r = client.post("/api/runs", headers=h, json={"scenario_version_id": sc["latest_version"]["id"]})
    wait_run(client, r.json()["id"], headers=h)
    ex = client.post("/api/lab/explain", headers=h, json={"sql": "SELECT * FROM lab.accounts WHERE id = 1"})
    assert ex.status_code == 200 and any("Seq Scan" in line or "Index" in line for line in ex.json()["plan"])
    schema = client.get("/api/lab/schema", headers=h)
    assert schema.status_code == 200
