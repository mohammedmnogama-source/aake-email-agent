"""Tests for the suggested_tasks staging repository.

These prove the staging layer works WITHOUT any ERP call or CRM write:
- create a staged proposal
- list pending proposals
- edit payload/content
- reject a proposal
- cannot mark executed twice (double-execution guard)
- no ERP module is imported / called
- no CRM tables (deals, customers, contacts, deal_items) are written
"""

import tempfile
from pathlib import Path

import pytest

from backend.database import connection
from backend.database.connection import get_connection, init_db
from backend.database.repositories import suggested_tasks as repo


@pytest.fixture()
def conn():
    """Fresh temp DB with all migrations applied, plus a seed email + suggestion
    (suggested_tasks has NOT NULL FKs to both).

    FK enforcement stays ON (the connection default). Migration 020 fixed the
    old `emails_v7` FK artifact (error log #1), so a fresh-from-migrations DB now
    references `emails` correctly and these inserts satisfy the FK chain.
    """
    tmp = tempfile.mkdtemp()
    db = str(Path(tmp) / "test.db")
    init_db(db)
    c = get_connection()
    c.execute(
        "INSERT INTO emails (subject, from_address, body_text) VALUES (?,?,?)",
        ("RFQ", "buyer@example.com", "Please quote 10 laptops"),
    )
    email_id = c.execute("SELECT id FROM emails").fetchone()["id"]
    c.execute(
        """INSERT INTO ai_suggestions
           (email_id, model_used, category, suggested_action, reasoning)
           VALUES (?,?,?,?,?)""",
        (email_id, "test", "customer_inquiry", "draft_reply", "test"),
    )
    c.commit()
    yield c
    c.close()
    connection._DB_PATH = None


def _seed(c, **over):
    email_id = c.execute("SELECT id FROM emails LIMIT 1").fetchone()["id"]
    sug_id = c.execute("SELECT id FROM ai_suggestions LIMIT 1").fetchone()["id"]
    data = {
        "email_id": email_id,
        "suggestion_id": sug_id,
        "task_type": "create_deal",
        "description": "Create deal for 10 laptops",
        "confidence": 0.8,
        "evidence_quote": "Please quote 10 laptops",
        "payload": {"qty": 10, "product": "laptop"},
    }
    data.update(over)
    return repo.create(c, data)


def test_create_staged_proposal(conn):
    tid = _seed(conn)
    row = repo.get(conn, tid)
    assert row is not None
    assert row["task_type"] == "create_deal"
    assert row["approved"] == 0
    assert row["executed_at"] is None
    assert row["erp_reference"] is None
    assert '"qty": 10' in row["payload"]
    assert row["confidence"] == 0.8


def test_exists_similar(conn):
    email_id = conn.execute("SELECT id FROM emails LIMIT 1").fetchone()["id"]
    sug_id = conn.execute("SELECT id FROM ai_suggestions LIMIT 1").fetchone()["id"]
    assert repo.exists_similar(conn, email_id, sug_id, "create_deal") is False
    _seed(conn, task_type="create_deal")
    assert repo.exists_similar(conn, email_id, sug_id, "create_deal") is True
    # different task_type is not a duplicate
    assert repo.exists_similar(conn, email_id, sug_id, "create_rfq") is False


def test_list_pending(conn):
    _seed(conn)
    _seed(conn, description="second")
    pending = repo.list_pending(conn)
    assert len(pending) == 2
    # rejected ones drop out of pending
    repo.reject(conn, pending[0]["id"])
    assert len(repo.list_pending(conn)) == 1


def test_edit_payload(conn):
    tid = _seed(conn)
    ok = repo.update(conn, tid, {"payload": {"qty": 25}, "description": "edited"})
    assert ok
    row = repo.get(conn, tid)
    assert '"qty": 25' in row["payload"]
    assert row["description"] == "edited"


def test_edit_ignores_protected_fields(conn):
    tid = _seed(conn)
    # trying to sneak in executed_at / erp_reference must be ignored
    repo.update(conn, tid, {"executed_at": "2026-01-01", "erp_reference": "HACK"})
    row = repo.get(conn, tid)
    assert row["executed_at"] is None
    assert row["erp_reference"] is None


def test_reject_proposal(conn):
    tid = _seed(conn)
    assert repo.reject(conn, tid) is True
    assert repo.get(conn, tid)["approved"] == -1


def test_approve_only_sets_flag(conn):
    tid = _seed(conn)
    assert repo.set_approved(conn, tid) is True
    row = repo.get(conn, tid)
    assert row["approved"] == 1
    # approve must NOT execute anything
    assert row["executed_at"] is None
    assert row["erp_reference"] is None


def test_cannot_mark_executed_twice(conn):
    tid = _seed(conn)
    repo.mark_executed(conn, tid, "ERP-123")
    row = repo.get(conn, tid)
    assert row["executed_at"] is not None
    assert row["erp_reference"] == "ERP-123"
    with pytest.raises(repo.AlreadyExecutedError):
        repo.mark_executed(conn, tid, "ERP-999")
    # reference unchanged after the blocked second attempt
    assert repo.get(conn, tid)["erp_reference"] == "ERP-123"


def test_no_crm_tables_touched(conn):
    """The whole staging flow must not write any CRM table."""
    def counts():
        return {
            t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("deals", "customers", "contacts", "deal_items")
        }

    before = counts()
    tid = _seed(conn)
    repo.update(conn, tid, {"description": "x"})
    repo.set_approved(conn, tid)
    repo.mark_executed(conn, tid, "ERP-1")
    assert counts() == before


def test_repo_imports_no_erp(conn):
    """The staging repository layer itself must not import/call the ERP client.
    (The ERP client legitimately exists and is used only by the execute route.)"""
    import inspect

    src = inspect.getsource(repo)
    assert "erp_client" not in src
    assert "integrations.erp" not in src
    assert "X-AAKE-Agent-Secret" not in src


# --------------------------------------------------------------------------- #
# Execution state machine (migration 021)
# --------------------------------------------------------------------------- #

import uuid as _uuid


def _approved_task(c):
    """Seed a create_task proposal and approve it. Returns its id."""
    tid = _seed(c, task_type="create_task")
    assert repo.set_approved(c, tid) is True
    return tid


def _make_stale(c, tid, seconds=300):
    c.execute(
        "UPDATE suggested_tasks SET execution_claimed_at = datetime('now', ?) WHERE id = ?",
        (f"-{seconds} seconds", tid),
    )
    c.commit()


def test_new_suggestion_gets_uuid4_key(conn):
    tid = _seed(conn)
    key = repo.get(conn, tid)["agent_suggestion_key"]
    assert key and _uuid.UUID(key).version == 4


def test_key_is_stable_across_edit_and_state_changes(conn):
    tid = _approved_task(conn)
    key0 = repo.get(conn, tid)["agent_suggestion_key"]
    repo.update(conn, tid, {"description": "changed"})
    repo.set_approved(conn, tid)
    assert repo.get(conn, tid)["agent_suggestion_key"] == key0


def test_claim_requires_approved(conn):
    tid = _seed(conn, task_type="create_task")  # NOT approved
    assert repo.claim_execution(conn, tid) is None


def test_claim_requires_create_task_type(conn):
    tid = _seed(conn, task_type="create_deal")
    repo.set_approved(conn, tid)
    assert repo.claim_execution(conn, tid) is None


def test_single_claim_winner(conn):
    tid = _approved_task(conn)
    first = repo.claim_execution(conn, tid)
    assert first is not None
    row, attempt = first
    assert row["execution_status"] == "executing"
    assert row["execution_attempt_id"] == attempt
    # A second immediate claim (fresh executing) must lose.
    assert repo.claim_execution(conn, tid) is None


def test_fresh_executing_not_reclaimed(conn):
    tid = _approved_task(conn)
    repo.claim_execution(conn, tid)
    assert repo.claim_execution(conn, tid) is None


def test_stale_executing_reclaimed_with_new_attempt(conn):
    tid = _approved_task(conn)
    _row, attempt_a = repo.claim_execution(conn, tid)
    _make_stale(conn, tid)
    second = repo.claim_execution(conn, tid)
    assert second is not None
    _row2, attempt_b = second
    assert attempt_b != attempt_a


def test_old_attempt_cannot_reconcile_after_reclaim(conn):
    tid = _approved_task(conn)
    _r, attempt_a = repo.claim_execution(conn, tid)
    _make_stale(conn, tid)
    _r2, attempt_b = repo.claim_execution(conn, tid)
    assert repo.reconcile_executed(conn, tid, attempt_a, str(_uuid.uuid4())) is False
    assert repo.get(conn, tid)["executed_at"] is None
    good = str(_uuid.uuid4())
    assert repo.reconcile_executed(conn, tid, attempt_b, good) is True
    row = repo.get(conn, tid)
    assert row["executed_at"] is not None and row["erp_reference"] == good


def test_old_attempt_cannot_fail_after_reclaim(conn):
    tid = _approved_task(conn)
    _r, attempt_a = repo.claim_execution(conn, tid)
    _make_stale(conn, tid)
    _r2, attempt_b = repo.claim_execution(conn, tid)
    assert repo.mark_failed(conn, tid, attempt_a, "stale worker error") is False
    assert repo.get(conn, tid)["execution_status"] == "executing"


def test_reconcile_sets_uuid_and_executed_together(conn):
    tid = _approved_task(conn)
    _r, attempt = repo.claim_execution(conn, tid)
    ref = str(_uuid.uuid4())
    assert repo.reconcile_executed(conn, tid, attempt, ref) is True
    row = repo.get(conn, tid)
    assert row["execution_status"] == "executed"
    assert row["executed_at"] is not None
    assert row["erp_reference"] == ref
    assert row["error_message"] is None


def test_reconcile_refuses_blank_reference(conn):
    tid = _approved_task(conn)
    _r, attempt = repo.claim_execution(conn, tid)
    with pytest.raises(ValueError):
        repo.reconcile_executed(conn, tid, attempt, "")
    assert repo.get(conn, tid)["executed_at"] is None


def test_mark_failed_keeps_retryable(conn):
    tid = _approved_task(conn)
    _r, attempt = repo.claim_execution(conn, tid)
    assert repo.mark_failed(conn, tid, attempt, "boom") is True
    row = repo.get(conn, tid)
    assert row["execution_status"] == "failed"
    assert row["executed_at"] is None
    assert row["erp_reference"] is None
    assert row["error_message"] == "boom"
    assert repo.claim_execution(conn, tid) is not None  # human retry


def test_edit_resets_approval_and_execution(conn):
    tid = _approved_task(conn)
    _r, attempt = repo.claim_execution(conn, tid)
    repo.mark_failed(conn, tid, attempt, "boom")
    repo.update(conn, tid, {"description": "corrected"})
    row = repo.get(conn, tid)
    assert row["approved"] == 0
    assert row["execution_status"] == "pending"
    assert row["error_message"] is None
    assert row["execution_claimed_at"] is None
    assert row["execution_attempt_id"] is None


def test_executing_row_not_editable(conn):
    tid = _approved_task(conn)
    repo.claim_execution(conn, tid)
    with pytest.raises(repo.NotEditableError):
        repo.update(conn, tid, {"description": "nope"})


def test_executed_row_not_editable(conn):
    tid = _approved_task(conn)
    _r, attempt = repo.claim_execution(conn, tid)
    repo.reconcile_executed(conn, tid, attempt, str(_uuid.uuid4()))
    with pytest.raises(repo.NotEditableError):
        repo.update(conn, tid, {"description": "nope"})


def test_approve_rejects_executing(conn):
    tid = _approved_task(conn)
    repo.claim_execution(conn, tid)
    assert repo.set_approved(conn, tid) is False
    assert repo.get(conn, tid)["execution_status"] == "executing"


def test_reject_ignores_executing(conn):
    tid = _approved_task(conn)
    repo.claim_execution(conn, tid)
    assert repo.reject(conn, tid) is False
    assert repo.get(conn, tid)["approved"] == 1
