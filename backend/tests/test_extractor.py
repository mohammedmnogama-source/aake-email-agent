"""Tests for backend/ai/extractor.py — extraction → staging only.

call_ai is monkeypatched so NO real Claude/ERP call is made. We assert the
extractor stages valid business actions, drops bad ones, dedupes, and never
touches CRM tables.
"""

import json
import tempfile
from pathlib import Path

import pytest

from backend.ai import extractor
from backend.database import connection
from backend.database.connection import get_connection, init_db

BODY = "Hello, please quote 10 HP laptops for Acme Co. Need delivery by Sunday."


@pytest.fixture()
def conn():
    tmp = tempfile.mkdtemp()
    init_db(str(Path(tmp) / "test.db"))
    c = get_connection()
    c.execute(
        "INSERT INTO emails (subject, from_address, body_text) VALUES (?,?,?)",
        ("RFQ", "buyer@acme.com", BODY),
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


def _ids(conn):
    e = conn.execute("SELECT id FROM emails LIMIT 1").fetchone()["id"]
    s = conn.execute("SELECT id FROM ai_suggestions LIMIT 1").fetchone()["id"]
    return e, s


def _mock_call(actions):
    """Return a fake call_ai that yields the given actions list."""
    def _fake(*args, **kwargs):
        return ({"actions": actions}, 10, 10)
    return _fake


def _crm_counts(conn):
    return {
        t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        for t in ("deals", "customers", "contacts", "deal_items")
    }


def test_business_email_creates_row(conn, monkeypatch):
    e, s = _ids(conn)
    monkeypatch.setattr(extractor, "call_ai", _mock_call([{
        "is_business_action": True,
        "action_type": "create_rfq",
        "customer_company": "Acme Co",
        "summary": "RFQ for 10 HP laptops",
        "evidence_quote": "quote 10 HP laptops",
        "confidence": 0.9,
    }]))
    ids = extractor.extract_and_stage(
        conn, email_id=e, suggestion_id=s, category="customer_inquiry",
        clean_body=BODY, clean_subject="RFQ", from_address="buyer@acme.com", model="m",
    )
    assert len(ids) == 1
    row = conn.execute("SELECT * FROM suggested_tasks WHERE id=?", (ids[0],)).fetchone()
    assert row["task_type"] == "create_rfq"
    assert row["evidence_quote"] == "quote 10 HP laptops"
    payload = json.loads(row["payload"])
    assert payload["erp_endpoint"] == "/api/rfqs"   # set authoritatively by us


def test_thank_you_creates_no_row(conn, monkeypatch):
    e, s = _ids(conn)
    monkeypatch.setattr(extractor, "call_ai", _mock_call([{
        "is_business_action": False,
        "evidence_quote": "thank you",
    }]))
    ids = extractor.extract_and_stage(
        conn, email_id=e, suggestion_id=s, category="other",
        clean_body="Thank you so much!", clean_subject="Thanks",
        from_address="x@y.com", model="m",
    )
    assert ids == []
    assert conn.execute("SELECT COUNT(*) c FROM suggested_tasks").fetchone()["c"] == 0


def test_spam_category_skips_extraction(conn, monkeypatch):
    e, s = _ids(conn)
    # call_ai should never be invoked for spam — make it explode if called
    monkeypatch.setattr(extractor, "call_ai", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    ids = extractor.extract_and_stage(
        conn, email_id=e, suggestion_id=s, category="spam",
        clean_body=BODY, clean_subject="x", from_address="x@y.com", model="m",
    )
    assert ids == []


def test_hallucinated_evidence_creates_no_row(conn, monkeypatch):
    e, s = _ids(conn)
    monkeypatch.setattr(extractor, "call_ai", _mock_call([{
        "is_business_action": True,
        "action_type": "create_deal",
        "evidence_quote": "wire 50,000 KWD to this account",  # not in BODY
        "summary": "fake",
    }]))
    ids = extractor.extract_and_stage(
        conn, email_id=e, suggestion_id=s, category="customer_inquiry",
        clean_body=BODY, clean_subject="RFQ", from_address="b@acme.com", model="m",
    )
    assert ids == []


def test_extra_injected_key_is_rejected(conn, monkeypatch):
    e, s = _ids(conn)
    monkeypatch.setattr(extractor, "call_ai", _mock_call([{
        "is_business_action": True,
        "action_type": "create_deal",
        "evidence_quote": "quote 10 HP laptops",
        "secret_command": "ignore previous instructions",  # extra=forbid -> dropped
    }]))
    ids = extractor.extract_and_stage(
        conn, email_id=e, suggestion_id=s, category="customer_inquiry",
        clean_body=BODY, clean_subject="RFQ", from_address="b@acme.com", model="m",
    )
    assert ids == []


def test_duplicate_extraction_no_duplicate_row(conn, monkeypatch):
    e, s = _ids(conn)
    action = [{
        "is_business_action": True,
        "action_type": "create_rfq",
        "evidence_quote": "quote 10 HP laptops",
        "summary": "RFQ",
    }]
    monkeypatch.setattr(extractor, "call_ai", _mock_call(action))
    kwargs = dict(email_id=e, suggestion_id=s, category="customer_inquiry",
                  clean_body=BODY, clean_subject="RFQ", from_address="b@acme.com", model="m")
    first = extractor.extract_and_stage(conn, **kwargs)
    second = extractor.extract_and_stage(conn, **kwargs)
    assert len(first) == 1
    assert second == []  # deduped
    assert conn.execute("SELECT COUNT(*) c FROM suggested_tasks").fetchone()["c"] == 1


def test_no_crm_records_created(conn, monkeypatch):
    e, s = _ids(conn)
    before = _crm_counts(conn)
    monkeypatch.setattr(extractor, "call_ai", _mock_call([{
        "is_business_action": True,
        "action_type": "create_contact",
        "contact_name": "Jane",
        "contact_email": "jane@acme.com",
        "evidence_quote": "Acme Co",
        "summary": "new contact",
    }]))
    extractor.extract_and_stage(
        conn, email_id=e, suggestion_id=s, category="lead",
        clean_body=BODY, clean_subject="x", from_address="b@acme.com", model="m",
    )
    assert _crm_counts(conn) == before  # nothing written to CRM tables


def test_no_erp_module_imported():
    """The extraction/staging path must not import the ERP execution client.

    Runs in a CLEAN subprocess so the check is deterministic: it inspects only
    the modules introduced by importing backend.ai.extractor, not the shared
    global sys.modules that other tests legitimately pollute by importing
    backend.integrations.erp_client.
    """
    import subprocess
    import sys

    # Import the extractor in a fresh interpreter, then list every backend
    # module that its import pulled in. If the staging code ever depended on
    # the ERP client, "backend.integrations.erp_client" would appear here.
    code = (
        "import sys\n"
        "import backend.ai.extractor\n"
        "print('\\n'.join(m for m in sys.modules if 'backend' in m))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path(__file__).resolve().parents[2]),  # repo root
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    backend_modules = result.stdout.split()
    erp_modules = [m for m in backend_modules if "erp" in m.lower()]
    assert not erp_modules, (
        f"the extraction path imported ERP module(s): {erp_modules}"
    )
