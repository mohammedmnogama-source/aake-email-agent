# Task: Build an Email Inbox page inside the ERP

## What to build

Add a new page at `/emails` to the ERP (Aqeeq Intelligence).
Add it to the left sidebar navigation under **CRM** (between Leads and Activities).

This page pulls emails from a local AI email agent (FastAPI running at 
`http://localhost:8000`) and lets Mo take action on them directly inside the ERP —
without switching apps.

---

## The Email Agent API

All fetches must happen **client-side** (browser → localhost:8000).
Do NOT call this from server components or server actions — localhost:8000 is 
only reachable from Mo's browser, not from Vercel servers.

### Get all emails
```
GET http://localhost:8000/api/inbox
```
Returns array of email objects:
```ts
{
  id: number,
  subject: string,
  from_name: string,
  from_address: string,
  body_preview: string,       // first ~300 chars
  received_at: string,        // ISO timestamp
  is_read: number,            // 0 = unread, 1 = read
  category: 'lead' | 'customer_inquiry' | 'vendor_quote_request' | 'internal' | 'spam' | 'other',
  suggested_action: 'draft_reply' | 'summarize_only' | 'extract_lead_info' | 'create_rfq' | 'no_action',
  summary: string,            // Claude's 2-3 sentence summary
  draft_content: string,      // Claude's suggested reply (may be null)
}
```

### Get single email (full detail)
```
GET http://localhost:8000/api/inbox/{id}
```
Returns `{ email: {...}, suggestion: { summary, draft_content, category, ... } }`

### Mark as read
```
PATCH http://localhost:8000/api/inbox/{id}/read
```

### Trigger sync (fetch new emails from IMAP)
```
POST http://localhost:8000/api/inbox/sync
```
Returns immediately. The agent fetches + analyzes in the background.

### Check sync progress
```
GET http://localhost:8000/api/inbox/sync-status
```
```json
{ "running": true, "stage": "analyzing", "message": "Analyzing 3 of 12: 'RFQ for UPS'", "current": 3, "total": 12 }
```
`stage` values: `idle | fetching | analyzing | done | error`

---

## Page Layout

Two-panel layout (same pattern as other list pages in this ERP):

```
LEFT PANEL (40%)                    RIGHT PANEL (60%)
─────────────────────────────────   ──────────────────────────────────────
[Sync Inbox button]  [status]       [Selected email detail]

[Search bar]                        From: Arifa Shareef <arifa@...>
[Filter pills: All · Lead ·         Subject: Request for Cisco switches
 Customer · Vendor · Internal]      Received: 8 Jun 2026

[Email list]                        AI SUMMARY
  ● Bold = unread                   Customer is requesting a quote for...
  ○ Normal = read
  Category badge on right           ──────────────────────────────────────
                                    ERP ACTIONS
                                    [📋 Create RFQ] [👤 Save as Lead]
                                    [✅ Create Task]
                                    
                                    AI DRAFT (if exists)
                                    ──────────────────
                                    Dear Arifa, Thank you for...
                                    [📋 Copy draft]

                                    EMAIL BODY
                                    ──────────
                                    (raw email text, scrollable)
```

---

## Action Buttons — Show Contextually

Show buttons based on `category`:

| Category | Show |
|----------|------|
| `lead` | 📋 Create RFQ + 👤 Save as Lead + ✅ Create Task |
| `customer_inquiry` | 📋 Create RFQ + ✅ Create Task |
| `vendor_quote_request` | ✅ Create Task only |
| `internal` | ✅ Create Task only |
| `spam` | No buttons |
| `other` | 📋 Create RFQ + ✅ Create Task |

---

## What Each Button Does

### 📋 Create RFQ
Opens a pre-filled modal (same style as the one on /rfqs/new).

Pre-fill from email:
- **Subject/Title**: call `POST /api/suggest-title` with `{ summary, email_subject }` → use returned `title`
  - If that fails, fall back to the email subject
- **Description**: `email.summary`
- **Customer**: `email.from_name` → search existing customers by name
- **Date Received**: `email.received_at` (date part only, YYYY-MM-DD)
- **Notes**: `"Imported from Email Agent on [date]"`

When confirmed: use the existing `createRfq` Server Action (same one used on /rfqs/new).
On success: show toast "RFQ-2026-018 created" + link to the new RFQ.

### 👤 Save as Lead
Opens a small modal pre-filled from the email sender.

Pre-fill:
- **First name**: first word of `from_name`
- **Last name**: remaining words of `from_name`
- **Email**: `from_address`
- **Source**: `"email_agent"` (hardcoded, hidden)

When confirmed: insert directly into `leads` table via Supabase (use existing createLead 
Server Action if it exists, otherwise insert directly).
On success: show toast "Lead saved" + link to /leads.

### ✅ Create Task
Opens a small modal pre-filled:

- **Title**: `"Follow up: [email subject]"`
- **Description**: `email.summary`
- **Priority**: medium (dropdown — low/medium/high/urgent)
- **Due date**: tomorrow (date picker)

When confirmed: insert into `tasks` table via Supabase.
On success: show toast "Task created" + link to /tasks.

---

## Sync Button Behaviour

The "Sync Inbox" button:
1. POSTs to `http://localhost:8000/api/inbox/sync`
2. Polls `GET /api/inbox/sync-status` every second
3. Shows a live status bar: "Analyzing 3 of 12: 'RFQ for UPS...'" with a progress bar
4. When `stage === 'done'`: refresh the email list + show "Done — X fetched, Y analyzed"
5. If localhost:8000 is unreachable: show "Email Agent is not running — start it on your Mac first"

---

## Unread / Read State

- Emails where `is_read === 0` show with **bold subject** and a small blue dot
- When Mo clicks an email: call `PATCH http://localhost:8000/api/inbox/{id}/read`
  and update local state immediately (don't wait for a full reload)
- Show unread count badge next to "Emails" in the sidebar nav

---

## Error State

If `http://localhost:8000` is unreachable (agent not running):

Show a friendly message instead of the email list:
```
📴 Email Agent is offline
Start it on your Mac: open Terminal and run the email agent server.
[Retry]
```

---

## Notes for Implementation

1. All fetch calls to localhost:8000 must be in a **Client Component** (`'use client'`).
   Use `useEffect` to load emails on mount. Never call localhost from server components.

2. No auth token needed — the email agent endpoints are open (no JWT required).

3. The suggest-title API (`POST /api/suggest-title`) is on this ERP itself (Vercel).
   That call CAN be made server-side or client-side — it's the same origin.

4. Match the existing ERP design system exactly:
   - Same card/panel styles as other list pages
   - Same modal pattern as /rfqs/new
   - Same toast notifications
   - Same sidebar nav item style

5. Category badge colors to use:
   - lead → green
   - customer_inquiry → purple  
   - vendor_quote_request → blue
   - internal → gray
   - spam → red
   - other → slate
