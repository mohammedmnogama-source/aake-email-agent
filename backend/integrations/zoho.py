"""
Zoho CRM integration.
Creates Deals and Tasks automatically when emails are approved.
Uses OAuth2 refresh token — auto-refreshes access token when expired.
"""
import requests
from datetime import datetime, timedelta, timezone

from backend.config import settings

_access_token: str = ""
_token_expiry: datetime = datetime.min.replace(tzinfo=timezone.utc)

ZOHO_API = "https://www.zohoapis.com/crm/v2"
ZOHO_ACCOUNTS = "https://accounts.zoho.com/oauth/v2/token"


def _get_token() -> str:
    """Return a valid access token, refreshing if expired."""
    global _access_token, _token_expiry

    if _access_token and datetime.now(timezone.utc) < _token_expiry:
        return _access_token

    resp = requests.post(ZOHO_ACCOUNTS, data={
        "client_id": settings.zoho_client_id,
        "client_secret": settings.zoho_client_secret,
        "refresh_token": settings.zoho_refresh_token,
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    data = resp.json()
    _access_token = data["access_token"]
    _token_expiry = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600) - 60)
    return _access_token


def _headers() -> dict:
    return {"Authorization": f"Zoho-oauthtoken {_get_token()}"}


def create_deal(
    deal_name: str,
    stage: str = "Qualification",
    amount: float | None = None,
    account_name: str | None = None,
    description: str | None = None,
    closing_date: str | None = None,
) -> str | None:
    """Create a Deal in Zoho CRM. Returns the new Deal ID or None on failure."""
    if not settings.zoho_client_id:
        return None

    if not closing_date:
        closing_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    payload = {
        "Deal_Name": deal_name,
        "Stage": stage,
        "Owner": {"id": settings.zoho_owner_id},
        "Closing_Date": closing_date,
    }
    if amount:
        payload["Amount"] = amount
    if account_name:
        payload["Account_Name"] = account_name
    if description:
        payload["Description"] = description

    try:
        resp = requests.post(
            f"{ZOHO_API}/Deals",
            headers=_headers(),
            json={"data": [payload]},
        )
        resp.raise_for_status()
        result = resp.json()
        deal_id = result["data"][0]["details"]["id"]
        print(f"[zoho] Deal created: {deal_name} → {deal_id}")
        return deal_id
    except Exception as e:
        print(f"[zoho] Deal creation failed: {e}")
        return None


def create_task(
    subject: str,
    due_date: str | None = None,
    priority: str = "High",
    description: str | None = None,
    deal_id: str | None = None,
) -> str | None:
    """Create a Task in Zoho CRM. Optionally link to a Deal. Returns Task ID or None."""
    if not settings.zoho_client_id:
        return None

    if not due_date:
        due_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    payload = {
        "Subject": subject,
        "Due_Date": due_date,
        "Priority": priority,
        "Status": "Not Started",
    }
    if description:
        payload["Description"] = description
    if deal_id:
        payload["What_Id"] = deal_id
        payload["$se_module"] = "Deals"

    try:
        resp = requests.post(
            f"{ZOHO_API}/Tasks",
            headers=_headers(),
            json={"data": [payload]},
        )
        resp.raise_for_status()
        result = resp.json()
        task_id = result["data"][0]["details"]["id"]
        print(f"[zoho] Task created: {subject} → {task_id}")
        return task_id
    except Exception as e:
        print(f"[zoho] Task creation failed: {e}")
        return None


def sync_email_approval(
    email_subject: str,
    email_from: str,
    from_name: str,
    suggested_action: str,
    category: str,
    reasoning: str,
    extracted_data: dict | None = None,
) -> dict:
    """
    Called after an email is approved. Decides what to create in Zoho:
    - extract_lead_info  → Deal + Task
    - forward_to_vendor  → Task only
    - draft_reply        → Task only
    - summarize_only     → Task only (low priority)
    Returns dict with zoho_deal_id and zoho_task_id (either can be None).
    """
    results = {"zoho_deal_id": None, "zoho_task_id": None}

    sender = from_name or email_from
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    deal_id = None

    if suggested_action == "extract_lead_info":
        # Create a Deal for this lead
        company = (extracted_data or {}).get("company_name") or sender
        amount = (extracted_data or {}).get("estimated_value")
        deal_name = f"{company} — {email_subject[:60]}"

        deal_id = create_deal(
            deal_name=deal_name,
            stage="Qualification",
            amount=float(amount) if amount else None,
            account_name=company,
            description=f"From: {email_from}\nCategory: {category}\n\n{reasoning}",
            closing_date=next_week,
        )
        results["zoho_deal_id"] = deal_id

        task_subject = f"Follow up on lead: {company}"
        task_desc = f"Email: {email_subject}\nFrom: {email_from}\n\n{reasoning}"
        task_id = create_task(task_subject, due_date=tomorrow, priority="High",
                              description=task_desc, deal_id=deal_id)
        results["zoho_task_id"] = task_id

    elif suggested_action in ("forward_to_vendor", "draft_reply"):
        task_subject = f"Reply sent — {email_subject[:70]}"
        task_desc = f"Email from {sender} ({email_from})\nAction: {suggested_action}\n\n{reasoning}"
        task_id = create_task(task_subject, due_date=tomorrow, priority="High",
                              description=task_desc)
        results["zoho_task_id"] = task_id

    else:
        # summarize_only / no_action — low priority reminder
        task_subject = f"Review: {email_subject[:70]}"
        task_desc = f"From: {sender} ({email_from})\n\n{reasoning}"
        task_id = create_task(task_subject, due_date=next_week, priority="Normal",
                              description=task_desc)
        results["zoho_task_id"] = task_id

    return results
