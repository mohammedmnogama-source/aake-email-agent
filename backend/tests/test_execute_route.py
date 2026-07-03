"""Tests for POST /api/suggested-tasks/{id}/execute and the retired inbox route.

A minimal FastAPI app mounts only the suggested-tasks router; auth is overridden
and the ERP client is monkeypatched, so no real ERP/Railway/Vercel/prod DB is
touched.
"""

import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.database import connection as conn_mod
from backend.database.connection import get_connection, init_db
from backend.database.repositories import suggested_tasks as repo
from backend.integrations import erp_client
from backend.middleware.auth import require_auth
from backend.routers import suggested_tasks as st_router


@pytest.fixture()
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    init_db(str(Path(tmp) / "t.db"))
    c = get_connection()
    c.execute(
        "INSERT INTO emails (subject, from_address, body_text) VALUES (?,?,?)",
        ("RFQ", "buyer@example.com", "Please quote 10 laptops"),
    )
    eid = c.execute("SELECT id FROM emails").fetchone()["id"]
    c.execute(
        """INSERT INTO ai_suggestions (email_id, model_used, category, suggested_action, reasoning)
           VALUES (?,?,?,?,?)""",
        (eid, "test", "customer_inquiry", "draft_reply", "test"),
    )
    c.commit()

    app = FastAPI()
    app.include_router(st_router.router)
    app.dependency_overrides[require_auth] = lambda: None

    tc = TestClient(app, raise_server_exceptions=True)
    tc.email_id = eid  # type: ignore[attr-defined]
    tc.conn = c        # type: ignore[attr-defined]
    yield tc
    c.close()
    conn_mod._DB_PATH = None


def _mk(client, *, task_type="create_task", approved=True):
    c = client.conn
    sug = c.execute("SELECT id FROM ai_suggestions LIMIT 1").fetchone()["id"]
    tid = repo.create(c, {
        "email_id": client.email_id, "suggestion_id": sug,
        "task_type": task_type, "description": "Quote 10 laptops",
        "confidence": 0.9, "evidence_quote": "Please quote 10 laptops",
        "payload": {"urgency": "high", "deadline": "2026-07-15"},
    })
    if approved:
        repo.set_approved(c, tid)
    return tid


def _ok_erp(monkeypatch, task_uuid=None, duplicate=False, counter=None):
    task_uuid = task_uuid or str(uuid.uuid4())

    def fake(body):
        if counter is not None:
            counter.append(body)
        return {"id": task_uuid, "duplicate": duplicate}

    monkeypatch.setattr(erp_client, "create_task", fake)
    return task_uuid


def test_execute_missing_row_404(client):
    assert client.post("/api/suggested-tasks/99999/execute").status_code == 404


def test_execute_wrong_type_400(client, monkeypatch):
    _ok_erp(monkeypatch)
    tid = _mk(client, task_type="create_deal")
    assert client.post(f"/api/suggested-tasks/{tid}/execute").status_code == 400


def test_execute_unapproved_400(client, monkeypatch):
    _ok_erp(monkeypatch)
    tid = _mk(client, approved=False)
    assert client.post(f"/api/suggested-tasks/{tid}/execute").status_code == 400


def test_execute_success(client, monkeypatch):
    ref = _ok_erp(monkeypatch)
    tid = _mk(client)
    r = client.post(f"/api/suggested-tasks/{tid}/execute")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "executed" and body["erp_reference"] == ref
    row = repo.get(client.conn, tid)
    assert row["execution_status"] == "executed"
    assert row["erp_reference"] == ref


def test_repeated_click_no_second_erp_call(client, monkeypatch):
    calls = []
    ref = _ok_erp(monkeypatch, counter=calls)
    tid = _mk(client)
    r1 = client.post(f"/api/suggested-tasks/{tid}/execute")
    r2 = client.post(f"/api/suggested-tasks/{tid}/execute")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["erp_reference"] == ref
    assert len(calls) == 1  # second click did NOT call the ERP again


def test_concurrent_fresh_claim_conflicts(client, monkeypatch):
    _ok_erp(monkeypatch)
    tid = _mk(client)
    # Simulate another worker holding a fresh claim.
    repo.claim_execution(client.conn, tid)
    r = client.post(f"/api/suggested-tasks/{tid}/execute")
    assert r.status_code == 409


def test_duplicate_response_reconciles(client, monkeypatch):
    ref = _ok_erp(monkeypatch, duplicate=True)
    tid = _mk(client)
    r = client.post(f"/api/suggested-tasks/{tid}/execute")
    assert r.status_code == 200
    assert r.json()["duplicate"] is True
    assert repo.get(client.conn, tid)["erp_reference"] == ref


def test_failure_then_human_retry(client, monkeypatch):
    def boom(body):
        raise erp_client.ErpError("ERP returned HTTP 500")

    monkeypatch.setattr(erp_client, "create_task", boom)
    tid = _mk(client)
    r = client.post(f"/api/suggested-tasks/{tid}/execute")
    assert r.status_code == 502
    row = repo.get(client.conn, tid)
    assert row["execution_status"] == "failed"
    assert row["executed_at"] is None and row["erp_reference"] is None

    # Human retry after fixing the ERP.
    ref = _ok_erp(monkeypatch)
    r2 = client.post(f"/api/suggested-tasks/{tid}/execute")
    assert r2.status_code == 200 and r2.json()["erp_reference"] == ref


def test_config_error_returns_503_and_failed(client, monkeypatch):
    def unconfigured(body):
        raise erp_client.ErpConfigError("not configured")

    monkeypatch.setattr(erp_client, "create_task", unconfigured)
    tid = _mk(client)
    r = client.post(f"/api/suggested-tasks/{tid}/execute")
    assert r.status_code == 503
    assert repo.get(client.conn, tid)["execution_status"] == "failed"


def test_stale_claim_recovered_by_execute(client, monkeypatch):
    ref = _ok_erp(monkeypatch)
    tid = _mk(client)
    repo.claim_execution(client.conn, tid)
    # Make the claim stale so the execute button may reclaim it.
    client.conn.execute(
        "UPDATE suggested_tasks SET execution_claimed_at = datetime('now','-300 seconds') WHERE id=?",
        (tid,),
    )
    client.conn.commit()
    r = client.post(f"/api/suggested-tasks/{tid}/execute")
    assert r.status_code == 200 and r.json()["erp_reference"] == ref


def test_already_executed_returns_stored_uuid(client, monkeypatch):
    calls = []
    ref = _ok_erp(monkeypatch, counter=calls)
    tid = _mk(client)
    client.post(f"/api/suggested-tasks/{tid}/execute")
    assert len(calls) == 1
    # A later click just echoes the stored UUID, no ERP call.
    r = client.post(f"/api/suggested-tasks/{tid}/execute")
    assert r.status_code == 200 and r.json()["erp_reference"] == ref
    assert len(calls) == 1


def test_edit_executed_row_conflicts(client, monkeypatch):
    _ok_erp(monkeypatch)
    tid = _mk(client)
    client.post(f"/api/suggested-tasks/{tid}/execute")
    r = client.patch(f"/api/suggested-tasks/{tid}", json={"description": "changed"})
    assert r.status_code == 409
