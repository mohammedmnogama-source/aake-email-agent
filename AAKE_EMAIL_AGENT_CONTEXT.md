# AAKE Email Agent — Integration Context for Aqeeq Intelligence ERP

This document gives you complete visibility into the AAKE Email Agent,
a local AI-powered inbox tool built for Mohammed at AAKE Kuwait.
The ERP (Aqeeq Intelligence) is the master system.
The Email Agent is a slave/service — it processes emails and feeds structured data into the ERP.

---

## What the Email Agent Does

Mo receives business emails at **mohammednogama@aqeeqkw.com** (cPanel IMAP).
The agent:
1. Fetches new emails every 15 minutes automatically
2. Strips personal data (Civil IDs, IBANs, etc.) before sending to AI
3. Calls Claude (Anthropic) to classify, summarize, and draft a reply
4. Stores the result in a local SQLite database
5. Mo reviews in a simple inbox UI and approves/rejects drafts

Nothing ever auto-sends. Mo always approves.

---

## Where It Runs

| Component | URL | Notes |
|-----------|-----|-------|
| API (FastAPI) | `http://localhost:8000` | Always running on Mo's Mac when working |
| Inbox UI (Next.js) | `http://localhost:3000` | Local frontend |
| Database | `data/agent.db` | SQLite, local file |
| ChromaDB (RAG) | `data/chroma_db/` | 356 emails indexed for AI context |

**The API is local-only.** The ERP must make calls from the browser (client-side),
not from Vercel server-side functions, because `localhost:8000` is only reachable
from Mo's own computer.

CORS is configured to allow: `http://localhost:3000` and `https://frontend-gamma-seven-9d9hr1vyhv.vercel.app`

---

## Full API Reference

### List all processed emails
```
GET http://localhost:8000/api/inbox
```
Optional: `?status=decided` or `?limit=100`

**Response — array of:**
```json
{
  "id": 42,
  "subject": "Request for Quotation - Cisco switches",
  "from_address": "arifa.shareef@customer.com",
  "from_name": "Arifa Bi Naveed Akbar Shareef",
  "body_preview": "Dear Mo, we need a quote for...",
  "received_at": "2026-06-08T07:33:00+00:00",
  "status": "decided",
  "is_read": 1,
  "category": "lead",
  "suggested_action": "draft_reply",
  "summary": "Customer requesting a price quote for 10x Cisco Catalyst switches...",
  "draft_content": "Dear Arifa, Thank you for your inquiry..."
}
```

---

### Get single email (full detail + draft)
```
GET http://localhost:8000/api/inbox/{id}
```
**Response:**
```json
{
  "email": {
    "id": 42,
    "subject": "...",
    "from_address": "...",
    "from_name": "...",
    "body_text": "full email body here...",
    "received_at": "2026-06-08T07:33:00+00:00",
    "status": "decided",
    "is_read": 0
  },
  "suggestion": {
    "category": "lead",
    "suggested_action": "draft_reply",
    "summary": "2-3 sentence AI summary...",
    "draft_subject": "Re: Request for Quotation",
    "draft_to": "arifa.shareef@customer.com",
    "draft_content": "Full draft reply body...",
    "reasoning": "Why this action was chosen",
    "confidence_note": "Optional note if AI was unsure"
  }
}
```

---

### Trigger a sync (fetch + analyze new emails)
```
POST http://localhost:8000/api/inbox/sync
```
Starts a background job. Returns immediately.
Poll `/api/inbox/sync-status` every second to track progress.

**Sync status response:**
```json
{
  "running": true,
  "stage": "analyzing",
  "message": "Analyzing 3 of 12: 'Request for Quotation'",
  "current": 3,
  "total": 12,
  "fetched": 12,
  "analyzed": 2
}
```
`stage` values: `idle | fetching | analyzing | done | error`

---

### Mark email as read
```
PATCH http://localhost:8000/api/inbox/{id}/read
```

---

### Create RFQ in ERP from an email (existing bridge)
```
POST http://localhost:8000/api/inbox/{id}/send-to-erp
Content-Type: application/json

{
  "subject": "Supply of 10x Cisco Catalyst switches",
  "description": "Customer needs switches for a new office setup...",
  "notes": "Imported from email on 2026-06-08",
  "received_date": "2026-06-08",
  "customer_name": "Arifa Bi Naveed Akbar Shareef"
}
```
The email agent proxies this to the ERP's `/api/rfqs` endpoint server-side.

---

## Email Categories (what the AI assigns)

| Category | Meaning |
|----------|---------|
| `lead` | New potential customer asking about products |
| `customer_inquiry` | Existing customer with question or order follow-up |
| `vendor_quote_request` | Supplier/vendor pricing info (CC'd to Mo) |
| `internal` | From purchase@aqeeqkw.com or internal staff |
| `spam` | Junk |
| `other` | Doesn't fit above |

## Suggested Actions (what the AI recommends)

| Action | Meaning |
|--------|---------|
| `draft_reply` | AI has written a reply — Mo needs to approve |
| `summarize_only` | No reply needed, just read the summary |
| `extract_lead_info` | New lead — contact details extracted |
| `create_rfq` | AI flagged this as an RFQ that should go to the ERP |
| `no_action` | Nothing to do |

---

## Current State (as of 2026-06-08)

- **50 emails** processed and stored in the database
- **356 emails** indexed in ChromaDB for RAG (AI context)
  - 100 sent emails (Mo's writing style)
  - 203 inbox history emails
  - 53 newly processed emails
- **Auto-sync** running every 15 minutes
- **Test mode ON** — approved drafts write to `data/test_drafts/` files, not real IMAP
- **Vendors configured:** Redington, Maimoon, Ingram, Logicom, Mindware, Exclusive Networks, etc.

---

## Integration Already Built

### ERP → Email Agent (the email picker)
The ERP's `/rfqs/new` form has an "Import from Email" button.
It fetches `http://localhost:8000/api/inbox` and shows a picker modal.
User clicks an email → form auto-fills (subject, description, customer, date).

### Email Agent → ERP (send button, less used)
Each email in the agent has a "Send to ERP as RFQ" button.
Posts to `http://localhost:8000/api/inbox/{id}/send-to-erp` which proxies to `/api/rfqs`.

---

## What Is Coming Next (pipeline)

1. **Email threading** — group RE:/FW: chains into one conversation instead of separate rows
2. **Turn off test mode** — once Mo is ready, approved drafts go to real IMAP Drafts folder
3. **Smart RFQ button** — show "Create RFQ in ERP" prominently only when AI flags `create_rfq`
4. **Search + filter** — filter inbox by category (leads only, inquiries only, etc.)
5. **Unread badge** — show count on the Inbox nav link
6. **Auth wiring** — JWT middleware exists but not yet enforced on inbox endpoints

**Decided against:**
- ❌ Auto-push leads to ERP — Mo pushes manually only (no background processes)
- ❌ Pagination — inbox is capped at 50 emails, that's enough

---

## How to Push More Data from Email Agent to ERP

If you need more integration points, the email agent can:
- Expose additional endpoints (ask the email agent session)
- Automatically POST to the ERP when specific events happen (e.g. new lead detected)
- The ERP session should define what it needs and the email agent session will build it

The email agent session is at: `/Users/mohammedmustafa/Desktop/cLaude/email-agent`

---

## Key Rules (never break these)

- Nothing auto-sends from the email agent — Mo always approves
- PII (Civil IDs, IBANs, passwords) is stripped before AI sees the email
- Sent folder access is read-only
- Drafts go via IMAP APPEND only — no smtplib ever
