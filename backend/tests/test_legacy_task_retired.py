"""The old unauthenticated inbox Create Task path must be retired (HTTP 410),
while the RFQ and Lead paths remain registered and untouched."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.middleware.auth import require_auth
from backend.routers import inbox as inbox_router


def _client():
    app = FastAPI()
    app.include_router(inbox_router.router)
    app.dependency_overrides[require_auth] = lambda: None
    return TestClient(app, raise_server_exceptions=True)


def test_create_task_route_returns_410():
    r = _client().post("/api/inbox/1/create-task")
    assert r.status_code == 410


def test_rfq_and_lead_routes_still_registered():
    paths = {r.path for r in inbox_router.router.routes}
    assert "/api/inbox/{email_id}/send-to-erp" in paths
    assert "/api/inbox/{email_id}/save-as-lead" in paths


def test_tasks_url_constant_removed():
    # The hardcoded ERP tasks URL constant is gone; RFQ/leads constants remain.
    assert not hasattr(inbox_router, "_TASKS_URL")
    assert hasattr(inbox_router, "_ERP_URL")
    assert hasattr(inbox_router, "_LEADS_URL")
