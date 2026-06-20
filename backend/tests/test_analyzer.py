"""Integration tests for analyzer Step 8.7 (business extraction wiring).

All AI/RAG calls are monkeypatched so nothing hits the network. We assert:
- a business email ends up with a suggested_tasks staging row
- if extraction raises, _analyze_one still completes (sync not broken)
"""

import tempfile
from pathlib import Path

import pytest

from backend.ai import analyzer, extractor
from backend.database import connection
from backend.database.connection import get_connection, init_db

BODY = "Hello, please quote 10 HP laptops for Acme Co."


@pytest.fixture()
def conn():
    tmp = tempfile.mkdtemp()
    init_db(str(Path(tmp) / "test.db"))
    c = get_connection()
    c.execute(
        "INSERT INTO emails (subject, from_address, from_name, body_text, status, source) "
        "VALUES (?,?,?,?,?,?)",
        ("RFQ", "buyer@acme.com", "Buyer", BODY, "pending", "imap"),
    )
    c.commit()
    yield c
    c.close()
    connection._DB_PATH = None


def _stub_context(monkeypatch):
    """Neutralise RAG / thread-summary / indexing so the test stays offline."""
    monkeypatch.setattr(analyzer, "_build_rag_context", lambda *a, **k: [])
    monkeypatch.setattr(analyzer, "_build_approved_context", lambda *a, **k: [])
    monkeypatch.setattr(analyzer, "_build_sent_context", lambda *a, **k: [])
    monkeypatch.setattr(analyzer, "build_thread_summary", lambda *a, **k: None)
    monkeypatch.setattr(analyzer.rag_store, "index_email", lambda *a, **k: None)


_CLASSIFY = {
    "category": "customer_inquiry",
    "suggested_action": "draft_reply",
    "reasoning": "r",
    "summary": "s",
    "draft_content": "Hi",
}


def _row(conn):
    return conn.execute(
        "SELECT id, subject, from_address, from_name, body_text, to_addresses "
        "FROM emails LIMIT 1"
    ).fetchone()


def test_business_email_creates_staging_row(conn, monkeypatch):
    _stub_context(monkeypatch)
    # classification call (used by analyzer)
    monkeypatch.setattr(analyzer, "call_ai", lambda *a, **k: (_CLASSIFY, 10, 10))
    # extraction call (used inside extractor)
    monkeypatch.setattr(extractor, "call_ai", lambda *a, **k: ({"actions": [{
        "is_business_action": True,
        "action_type": "create_rfq",
        "evidence_quote": "quote 10 HP laptops",
        "summary": "RFQ for 10 HP laptops",
        "confidence": 0.9,
    }]}, 10, 10))

    analyzer._analyze_one(conn, _row(conn), "m")

    rows = conn.execute("SELECT * FROM suggested_tasks").fetchall()
    assert len(rows) == 1
    assert rows[0]["task_type"] == "create_rfq"
    # email completed normally
    status = conn.execute("SELECT status FROM emails LIMIT 1").fetchone()["status"]
    assert status == "decided"


def test_extraction_failure_does_not_break_analyzer(conn, monkeypatch):
    _stub_context(monkeypatch)
    monkeypatch.setattr(analyzer, "call_ai", lambda *a, **k: (_CLASSIFY, 10, 10))

    def _boom(*a, **k):
        raise RuntimeError("extraction blew up")

    monkeypatch.setattr(extractor, "extract_and_stage", _boom)

    # must NOT raise
    analyzer._analyze_one(conn, _row(conn), "m")

    # email still decided, no staging rows
    status = conn.execute("SELECT status FROM emails LIMIT 1").fetchone()["status"]
    assert status == "decided"
    assert conn.execute("SELECT COUNT(*) c FROM suggested_tasks").fetchone()["c"] == 0
