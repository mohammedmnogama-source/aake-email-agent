"""Tests for the ERP client: field mapping + response validation.

No real network: httpx.post is monkeypatched. The real ERP, Railway, Vercel and
production DB are never touched.
"""

import json
import uuid

import httpx
import pytest

from backend.config import settings
from backend.integrations import erp_client
from backend.integrations.erp_client import (
    ErpConfigError,
    ErpError,
    build_task_payload,
    normalize_priority,
    valid_due_date,
)


@pytest.fixture()
def erp_configured(monkeypatch):
    monkeypatch.setattr(settings, "erp_base_url", "https://erp.example.com/", raising=False)
    monkeypatch.setattr(settings, "erp_shared_secret", "s3cr3t-not-logged", raising=False)


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _capture(monkeypatch, resp):
    calls = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        calls["headers"] = headers
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(erp_client.httpx, "post", fake_post)
    return calls


# ---------------- field mapping ----------------

def test_priority_normalization():
    assert normalize_priority("ASAP please") == "urgent"
    assert normalize_priority("this is important") == "high"
    assert normalize_priority("low, whenever") == "low"
    assert normalize_priority("something else") == "medium"
    assert normalize_priority(None) == "medium"


def test_due_date_validation():
    assert valid_due_date("2026-07-15") == "2026-07-15"
    assert valid_due_date("15/07/2026") is None
    assert valid_due_date("2026-13-40") is None
    assert valid_due_date("") is None
    assert valid_due_date(None) is None


def test_build_payload_shape_and_omissions():
    row = {
        "agent_suggestion_key": "key-123",
        "description": "Quote 10 laptops for ACME",
        "payload": json.dumps({
            "urgency": "urgent",
            "deadline": "2026-07-15",
            "customer_company": "ACME",
            "contact_name": "Sara",
            "email_id_should_not_appear": 999,
        }),
        # fields that must NEVER be forwarded:
        "id": 42,
        "email_id": 7,
    }
    body = build_task_payload(row)
    assert set(body.keys()) == {"agent_suggestion_key", "title", "description", "priority", "due_date"}
    assert body["agent_suggestion_key"] == "key-123"
    assert body["priority"] == "urgent"
    assert body["due_date"] == "2026-07-15"
    assert "ACME" in body["description"]
    # explicit contract: no relationship / local-id fields
    for forbidden in ("related_type", "related_id", "email_id", "id"):
        assert forbidden not in body


def test_build_payload_title_truncation_and_fallback():
    long = "x" * 500
    body = build_task_payload({"agent_suggestion_key": "k", "description": long, "payload": "{}"})
    assert len(body["title"]) <= 200
    body2 = build_task_payload({"agent_suggestion_key": "k", "description": "   ", "payload": "{}"})
    assert body2["title"] == "Create task from reviewed email suggestion"


def test_build_payload_omits_due_date_when_invalid():
    body = build_task_payload({
        "agent_suggestion_key": "k", "description": "d",
        "payload": json.dumps({"deadline": "next tuesday"}),
    })
    assert "due_date" not in body


# ---------------- network + response validation ----------------

def test_missing_config_raises(monkeypatch):
    monkeypatch.setattr(settings, "erp_base_url", "", raising=False)
    monkeypatch.setattr(settings, "erp_shared_secret", "", raising=False)
    with pytest.raises(ErpConfigError):
        erp_client.create_task({"agent_suggestion_key": "k", "title": "t"})


def test_success_sends_url_and_auth_header(erp_configured, monkeypatch):
    tid = str(uuid.uuid4())
    calls = _capture(monkeypatch, _Resp(200, {"ok": True, "id": tid, "reference": None}))
    out = erp_client.create_task({"agent_suggestion_key": "k", "title": "t"})
    assert out == {"id": tid, "duplicate": False}
    assert calls["url"] == "https://erp.example.com/api/tasks"       # trailing slash stripped
    assert calls["headers"]["X-AAKE-Agent-Secret"] == "s3cr3t-not-logged"


def test_secret_not_in_any_error_message(erp_configured, monkeypatch):
    _capture(monkeypatch, _Resp(401, {"ok": False}))
    with pytest.raises(ErpError) as ei:
        erp_client.create_task({"agent_suggestion_key": "k", "title": "t"})
    assert "s3cr3t-not-logged" not in str(ei.value)


def test_duplicate_true_is_success(erp_configured, monkeypatch):
    tid = str(uuid.uuid4())
    _capture(monkeypatch, _Resp(200, {"ok": True, "id": tid, "reference": None, "duplicate": True}))
    out = erp_client.create_task({"agent_suggestion_key": "k", "title": "t"})
    assert out == {"id": tid, "duplicate": True}


def test_401_raises_erp_error(erp_configured, monkeypatch):
    _capture(monkeypatch, _Resp(401, {"ok": False}))
    with pytest.raises(ErpError):
        erp_client.create_task({"agent_suggestion_key": "k", "title": "t"})


def test_timeout_raises_erp_error(erp_configured, monkeypatch):
    _capture(monkeypatch, httpx.TimeoutException("slow"))
    with pytest.raises(ErpError):
        erp_client.create_task({"agent_suggestion_key": "k", "title": "t"})


def test_invalid_json_raises(erp_configured, monkeypatch):
    _capture(monkeypatch, _Resp(200, ValueError("bad json")))
    with pytest.raises(ErpError):
        erp_client.create_task({"agent_suggestion_key": "k", "title": "t"})


def test_invalid_uuid_raises(erp_configured, monkeypatch):
    _capture(monkeypatch, _Resp(200, {"ok": True, "id": "not-a-uuid"}))
    with pytest.raises(ErpError):
        erp_client.create_task({"agent_suggestion_key": "k", "title": "t"})


def test_ok_false_raises(erp_configured, monkeypatch):
    _capture(monkeypatch, _Resp(200, {"ok": False, "id": str(uuid.uuid4())}))
    with pytest.raises(ErpError):
        erp_client.create_task({"agent_suggestion_key": "k", "title": "t"})
