"""Server-side client for the Aqeeq ERP Create Task endpoint.

Sends ONE authenticated POST /api/tasks using the shared secret. Nothing here
retries automatically, logs the secret, or returns raw response bodies/headers.
The Email Agent's local suggested_tasks.id, email_id, related_type and
related_id are deliberately NOT sent in v1.

All failures are surfaced as ErpError with a short sanitized message safe to
store in error_message and show to the user.
"""

import json
import re
import uuid

import httpx

from backend.config import settings

# ERP contract: agent_suggestion_key is the cross-system idempotency identity.
_ERP_TIMEOUT_SECONDS = 15.0
_TITLE_MAX = 200
_DESCRIPTION_MAX = 2000
_TITLE_FALLBACK = "Create task from reviewed email suggestion"
_VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ErpConfigError(Exception):
    """ERP_BASE_URL / ERP_SHARED_SECRET is not configured."""


class ErpError(Exception):
    """Any sanitized ERP failure (auth, network, bad response, etc.)."""


# --------------------------------------------------------------------------- #
# Field mapping helpers (pure — unit tested without the network)
# --------------------------------------------------------------------------- #

def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    # Deterministic truncation with a single-char ellipsis.
    return text[: limit - 1].rstrip() + "…"


def normalize_priority(raw: str | None) -> str:
    """Map free-text urgency to the ERP's low|medium|high|urgent vocabulary."""
    v = (raw or "").strip().lower()
    if any(w in v for w in ("urgent", "asap", "immediately", "critical")):
        return "urgent"
    if any(w in v for w in ("high", "important", "priority")):
        return "high"
    if any(w in v for w in ("low", "whenever", "no rush")):
        return "low"
    return "medium"


def valid_due_date(raw: str | None) -> str | None:
    """Return a strictly valid YYYY-MM-DD date, else None (field omitted)."""
    v = (raw or "").strip()
    if not _ISO_DATE_RE.match(v):
        return None
    y, m, d = (int(p) for p in v.split("-"))
    try:
        import datetime

        datetime.date(y, m, d)
    except ValueError:
        return None
    return v


def _compose_description(description: str, payload: dict) -> str:
    """Build a labelled plain-text description from safe structured fields only.
    Never dumps the raw email body."""
    lines: list[str] = []
    summary = (description or "").strip()
    if summary:
        lines.append(f"Summary: {summary}")

    company = payload.get("customer_company")
    if company:
        lines.append(f"Customer: {company}")

    contact_bits = [payload.get("contact_name"), payload.get("contact_email"),
                    payload.get("contact_phone")]
    contact = " · ".join(str(b) for b in contact_bits if b)
    if contact:
        lines.append(f"Contact: {contact}")

    if payload.get("urgency"):
        lines.append(f"Urgency: {payload['urgency']}")
    if payload.get("deadline"):
        lines.append(f"Deadline: {payload['deadline']}")

    missing = payload.get("missing_information")
    if isinstance(missing, list) and missing:
        lines.append("Missing info: " + "; ".join(str(m) for m in missing))

    return _truncate("\n".join(lines), _DESCRIPTION_MAX)


def build_task_payload(row: dict) -> dict:
    """Build the exact v1 ERP payload from a staged suggested_tasks row.

    Only agent_suggestion_key, title, description, priority and (when valid)
    due_date are sent. No email_id, related_type, related_id, local id or
    attempt id.
    """
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    title = _truncate(row.get("description") or "", _TITLE_MAX) or _TITLE_FALLBACK
    body = {
        "agent_suggestion_key": row["agent_suggestion_key"],
        "title": title,
        "description": _compose_description(row.get("description") or "", payload),
        "priority": normalize_priority(payload.get("urgency")),
    }
    due = valid_due_date(payload.get("deadline"))
    if due:
        body["due_date"] = due
    return body


# --------------------------------------------------------------------------- #
# Network call + response validation
# --------------------------------------------------------------------------- #

def _base_url() -> str:
    base = (settings.erp_base_url or "").strip()
    secret = (settings.erp_shared_secret or "").strip()
    if not base or not secret:
        raise ErpConfigError("ERP integration is not configured")
    return base.rstrip("/")


def _is_uuid(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def create_task(body: dict) -> dict:
    """POST one task to the ERP and return {"id": <uuid>, "duplicate": bool}.

    Raises ErpConfigError when unconfigured, ErpError (sanitized) on any auth /
    network / protocol failure. Never logs or returns the secret, headers, or
    raw response bodies.
    """
    base = _base_url()  # raises ErpConfigError if unconfigured
    url = f"{base}/api/tasks"
    headers = {
        "X-AAKE-Agent-Secret": settings.erp_shared_secret,
        "Content-Type": "application/json",
    }

    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=_ERP_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        raise ErpError("ERP request timed out")
    except httpx.HTTPError:
        raise ErpError("Could not reach ERP")

    if resp.status_code == 401:
        raise ErpError("ERP rejected the agent credentials (401)")
    if resp.status_code != 200:
        raise ErpError(f"ERP returned HTTP {resp.status_code}")

    try:
        data = resp.json()
    except (ValueError, json.JSONDecodeError):
        raise ErpError("ERP returned invalid JSON")
    if not isinstance(data, dict):
        raise ErpError("ERP returned an unexpected response shape")
    if data.get("ok") is not True:
        raise ErpError("ERP reported the task was not created")

    task_id = data.get("id")
    if not _is_uuid(task_id):
        raise ErpError("ERP response missing a valid task id")

    return {"id": task_id, "duplicate": bool(data.get("duplicate"))}
