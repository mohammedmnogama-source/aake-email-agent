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

    NOTE: FK enforcement is turned OFF on this connection. A pre-existing
    artifact in 000_baseline_rebuilt.sql makes a fresh-from-migrations DB
    reference a non-existent `emails_v7` (the SQLite FK auto-rename bug, error
    log #1). The REAL production DB references `emails` correctly, so this is a
    fresh-build-only quirk. These tests exercise the staging repo's logic, not
    FK integrity, so disabling FK checks here is safe and keeps scope minimal.
    """
    tmp = tempfile.mkdtemp()
    db = str(Path(tmp) / "test.db")
    init_db(db)
    c = get_connection()
    c.execute("PRAGMA foreign_keys = OFF")
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
    """The repository must not pull in any ERP client module."""
    import sys

    assert not any("erp" in m.lower() for m in sys.modules if "backend" in m), (
        "an ERP module was imported by the staging layer"
    )
