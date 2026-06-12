# AAKE Email Agent — Tomorrow's Briefing
Last updated: 2026-06-08 (read before starting any session)

---

## What This App Is (Plain English)

You are Mohammed at AAKE Kuwait. AAKE buys IT equipment wholesale from suppliers
(Redington, Ingram, Westcon, etc.) and resells it to customers (government, companies in Kuwait).

Your daily work:
1. Customer emails asking for a price on Cisco/Fortinet/HP/Microsoft gear
2. You ask your suppliers for their price
3. You quote the customer with your markup
4. Customer sends a Purchase Order → you send PO to supplier → deal done

This app automates the boring part of that:
- Reads your cPanel inbox automatically
- AI (Claude) reads each email, says what it is, and writes a draft reply for you
- You review the draft → click Approve → it saves to your email Drafts folder
- You also track each deal from inquiry to purchase order in the Deals section

Nothing ever auto-sends. You always review first.

---

## How the App Works (The Pipeline)

When you click "Sync Inbox":

```
Your cPanel Inbox (IMAP)
        ↓
    fetcher.py          ← downloads new emails → stores in SQLite DB
        ↓
    analyzer.py         ← for each new email:
        ↓
    redactor.py         ← strips Kuwait Civil IDs, IBANs, card numbers (before sending to Claude)
        ↓
    rag/store.py        ← asks ChromaDB: "find 3 similar emails we handled before"
        ↓
    deal_ai.py          ← loads your writing style (if confirmed in Settings)
        ↓
    gemini_client.py    ← sends everything to Claude API → gets JSON back:
                           { category, suggested_action, summary, draft_reply }
        ↓
    ai_suggestions DB   ← saves the result
        ↓
    rag/store.py        ← indexes this new email into ChromaDB for future queries
        ↓
    Inbox page          ← you see the email + AI summary + draft reply
```

---

## Every File Explained

### Backend (Python — the brain)

| File | What it does |
|------|-------------|
| `backend/main.py` | Starts the FastAPI server. Loads DB. Registers all routes. Port 8000. |
| `backend/config.py` | Reads your `.env` file: email password, Claude API key, JWT secret |
| `backend/database/connection.py` | Opens SQLite, runs all migrations on startup |
| `backend/database/migrations/` | 11 SQL files that built the database schema (never edit applied ones) |
| `backend/database/repositories/` | One file per table: functions to read/write data |
| `backend/email/fetcher.py` | Connects to cPanel IMAP, downloads emails newer than last sync UID |
| `backend/email/draft_saver.py` | Saves draft emails via IMAP APPEND — NO smtplib, ever |
| `backend/email/style_learner.py` | Reads your last 50 sent emails → asks Claude to describe your writing style |
| `backend/email/imap_client.py` | Reusable IMAP connection helper (used by fetcher, style_learner, store) |
| `backend/ai/analyzer.py` | THE BRAIN. Runs the full pipeline on every pending email |
| `backend/ai/gemini_client.py` | Calls Claude API (legacy filename — uses anthropic SDK, not Gemini) |
| `backend/ai/deal_ai.py` | Deal-specific AI: extract deal from pasted email/PDF, draft supplier & customer emails |
| `backend/ai/redactor.py` | Regex patterns that strip PII before sending to Claude |
| `backend/ai/models.py` | Defines valid email categories and actions as Python enums |
| `backend/rag/store.py` | ChromaDB "filing cabinet": save emails as vectors, find similar past emails |
| `backend/routers/inbox.py` | API: POST /sync, POST /backfill, GET /inbox, GET /inbox/{id} |
| `backend/routers/deals.py` | API: full deal lifecycle — create, items, supplier requests, quotes, POs |
| `backend/routers/style.py` | API: paste/refresh/confirm writing style |
| `backend/routers/settings.py` | API: get/update settings, change password, view audit log |
| `backend/middleware/auth.py` | JWT auth — creates and validates login tokens |

### Frontend (Next.js — the dashboard, port 3000)

| Page | URL | What it does |
|------|-----|-------------|
| Inbox | `/inbox` | Email list + AI summary + draft reply. Has "Sync" and "Learn" buttons |
| Deals | `/deals` | Table of all deals with status badges |
| New Deal | `/deals/new` | Create a deal: manual form OR paste email OR upload PDF |
| Deal Detail | `/deals/[id]` | Full deal: line items, supplier requests, quotes, POs, AI next step |
| Settings | `/settings` | Toggle test mode, AI model, writing style learner, change password |
| Login | `/login` | bcrypt password → JWT token stored in localStorage |

### Database Tables (SQLite at `data/agent.db`)

| Table | What it stores |
|-------|---------------|
| `emails` | Every fetched/pasted email. Status: pending → processing → decided |
| `ai_suggestions` | Claude's analysis: category, action, summary, draft_reply |
| `deals` | Each deal (inquiry to PO). Status: inquiry → sourcing → quoted → won → fulfilled |
| `deal_items` | Products per deal (name, qty, specs) |
| `deal_supplier_requests` | Requests you sent to suppliers (with AI-drafted email text) |
| `deal_supplier_quotes` | Quotes you received back from suppliers |
| `deal_customer_quotes` | Quotes you sent to customers |
| `deal_customer_pos` | Customer purchase orders (marks deal as "won") |
| `deal_supplier_pos` | Supplier purchase orders you issued |
| `vendors` | Your supplier companies (Redington, Ingram, etc.) |
| `customers` | Your customer companies |
| `settings` | App config: AI model, test mode, target folder, sent folder, etc. |
| `writing_style` | Your writing style profile (extracted from sent emails by Claude) |
| `style_examples` | Sample email bodies used to show Claude your style |
| `api_audit_log` | Every Claude API call: timestamp, model, purpose, sizes (no content) |
| `manually_handled_patterns` | Sender domains to skip — Mo handles these himself |
| `imap_sync` | Tracks the last email UID fetched per folder (for incremental fetching) |

### ChromaDB (`data/chroma_db/`)

ChromaDB is a separate "vector database" (a second database just for finding similar emails).

- Think of it like Google but for your emails: you give it a new email, it finds the 3 most similar past ones
- It converts email text into a list of 384 numbers (called a "vector/embedding") that represent the meaning
- Similar-meaning emails have similar numbers → it finds the closest match
- Embedding model: `all-MiniLM-L6-v2` (~23MB, runs on your Mac, downloaded once)
- Inbox emails stored with positive IDs (1, 2, 3...)
- Sent emails stored with negative IDs (-uid) to avoid clashing with inbox IDs
- Currently: **0 emails indexed** (needs backfill — see Task 1 below)

---

## Current State of the App (as of tonight)

| Thing | Status |
|-------|--------|
| Emails in DB | 3 (all analyzed, status=decided) |
| AI suggestions | 3 |
| Deals | 3 |
| Vendors in DB | 0 ← PROBLEM: tone detection always says "customer" |
| Customers in DB | 0 |
| ChromaDB emails | 0 ← PROBLEM: RAG not working (no past emails to compare against) |
| Writing style | Need to check if confirmed |
| Test mode | ON (approvals write to files, not real Drafts folder) |
| Auth on inbox routes | NOT wired up yet (anyone with server access can call the API) |

---

## Problems That Need Fixing Tomorrow

### Problem 1 — ChromaDB is empty (RAG not working)
**What this means:** When a new email arrives, Claude has NO past emails to compare against.
The system still works but Claude's context is weaker — it doesn't know "last time we got
a Redington quote, we replied like this."

**Fix:** Click "Learn from sent emails" on the Inbox page. This indexes:
- Your 3 existing inbox emails into ChromaDB
- Up to 100 of your sent emails from IMAP
Takes ~2 minutes. Do this first thing tomorrow.

### Problem 2 — No vendors in the database
**What this means:** `analyzer.py` checks the vendors table to decide if a sender is a
"supplier" or "customer." With 0 vendors, everyone is treated as a customer, so
supplier emails get a customer-tone draft reply.

**Fix:** Go to localhost:3000/vendors and add your main suppliers
(Redington, Ingram Micro, Westcon, Logicom, any others).

### Problem 3 — Approve button doesn't exist yet (T9)
**What this means:** You can see the AI draft reply but there is no button to save it
to your email Drafts folder. You have to copy-paste it manually.

**Fix:** Build the Approve button (Task 4 in tomorrow's plan below).

---

## Tomorrow's To-Do List (Priority Order)

**GOAL: By end of tomorrow, you can receive a real email, see the AI draft,
click Approve, and find the draft in your cPanel Drafts folder ready to send.**

---

### Task 1 — Populate ChromaDB (15 minutes) ← DO THIS FIRST
**What:** Index all your existing emails so RAG works.
**How:**
1. Open `localhost:3000/inbox`
2. Click "Learn from sent emails"
3. Wait ~2 minutes (it reads your sent folder from cPanel)
4. The button will say "Backfill complete" when done

**How to verify it worked:**
Run this in terminal:
```bash
cd /Users/mohammedmustafa/Desktop/cLaude/email-agent
.venv/bin/python -c "
import chromadb
c = chromadb.PersistentClient(path='data/chroma_db')
col = c.get_collection('emails')
print('Emails in ChromaDB:', col.count())
"
```
Should show a number > 0.

---

### Task 2 — Add vendors to the database (10 minutes)
**What:** Add your suppliers so the AI knows whose emails are "supplier tone" vs "customer tone."
**How:**
1. Open `localhost:3000/vendors`
2. Add each supplier you deal with (at minimum: Redington, Ingram Micro)
3. Include their email domain (e.g. `redington.com`)

---

### Task 3 — Test the full sync pipeline (20 minutes)
**What:** Send yourself a test email (or wait for a real one), then sync and verify the AI analysis works correctly.
**How:**
1. Send a test email to your cPanel inbox (something like "I need a quote for 5 Cisco switches")
2. Click "Sync Inbox" on the Inbox page
3. Wait ~30 seconds for fetch + analysis
4. Click the new email in the list
5. Check: Does the summary make sense? Does the draft reply sound right? Is the category correct?

**What a good result looks like:**
- Category: `lead` or `customer_inquiry`
- Summary: 2-3 sentences about what they need
- Draft reply: professional, mentions getting back with a quote
- If ChromaDB has past emails: the draft should feel more contextual

---

### Task 4 — Build the Approve button (1–2 hours) ← MOST IMPORTANT FEATURE
**What:** A button on the Inbox page that saves the AI draft to your cPanel Drafts folder via IMAP.
This is the key workflow: AI writes draft → you review → click Approve → open your email and hit Send.

**Files to change:**
1. `backend/routers/inbox.py` — add new endpoint:
   ```
   POST /api/inbox/{email_id}/approve
   → calls draft_saver.save_draft(to, subject, body)
   → returns { "saved": true, "uid": <draft uid> }
   ```
2. `frontend/app/inbox/page.tsx` — add "Save to Drafts" button in the detail panel
   below the draft preview, next to "Copy draft"

**Test mode note:** When test_mode=1 (currently ON), it writes to `data/test_drafts/` instead of real IMAP.
Turn off test mode in Settings before doing a real end-to-end test.

---

### Task 5 — Tone split: customer vs supplier style (1–2 hours)
**What:** Currently one writing style profile for all emails. We want two:
- Supplier tone: formal, technical, brief ("Dear [Name], Please provide pricing for...")
- Customer tone: warmer, friendlier, relationship-focused

**Files to change:**
1. `backend/database/migrations/012_tone_split.sql` — add `tone_type TEXT DEFAULT 'general'` to `writing_style`
2. `backend/email/style_learner.py` — extract TWO profiles from sent emails (customer-facing vs supplier-facing)
3. `backend/ai/deal_ai.py` — update `_build_style_block()` to accept a `tone_type` parameter
4. `backend/ai/analyzer.py` — pass `tone_type` to `_build_style_block()`

---

### Task 6 — Wire up auth on inbox routes (30 minutes)
**What:** Right now anyone who knows the server address can call `/api/inbox` without logging in.
Need to add the JWT auth check to the inbox router.

**File to change:**
`backend/routers/inbox.py` — add `require_auth` dependency to each endpoint, same pattern as other routers.

---

## Priority Summary

| Priority | Task | Time | Why |
|----------|------|------|-----|
| NOW | Task 1: Populate ChromaDB | 15 min | RAG is broken without it |
| NOW | Task 2: Add vendors | 10 min | Tone detection is broken |
| HIGH | Task 3: Test full pipeline | 20 min | Verify everything works together |
| HIGH | Task 4: Approve button | 1-2 hrs | Core feature you actually need |
| MEDIUM | Task 5: Tone split | 1-2 hrs | Better draft quality |
| MEDIUM | Task 6: Wire up auth | 30 min | Security |

**Realistic goal for one day:** Tasks 1–4.

---

## How to Start the App Tomorrow

Open two terminals:

**Terminal 1 — Backend:**
```bash
cd /Users/mohammedmustafa/Desktop/cLaude/email-agent
.venv/bin/uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd /Users/mohammedmustafa/Desktop/cLaude/email-agent/frontend
npm run dev
```

Then open Chrome: `http://localhost:3000`

---

## Things That Will NEVER Change (Hard Rules in the Code)

1. **No smtplib** — Drafts are saved via IMAP APPEND only (`draft_saver.py`)
2. **Sent folder is read-only** — `readonly=True` is enforced in `style_learner.py` and `rag/store.py`
3. **PII is always redacted before Claude** — `redact()` runs in `analyzer.py` AND inside `rag/store.py`
4. **Nothing auto-sends** — Mo always reviews and approves
5. **Never edit applied migration files** — always add a new numbered `.sql` file

---

## Questions You Might Ask Tomorrow

**Q: Why does the AI draft sometimes sound generic?**
A: Either ChromaDB is empty (no past emails to reference) or writing style isn't confirmed in Settings. Fix: Task 1 + go to Settings → Refresh Style → Confirm.

**Q: Why is a vendor email being treated as a customer?**
A: The vendors table is empty. Fix: Task 2 — add vendors to localhost:3000/vendors.

**Q: Where do approved drafts go?**
A: When test_mode=ON → `data/test_drafts/` folder on your Mac. When test_mode=OFF → your real cPanel Drafts folder (you'll see it in your email client).

**Q: What is the AI model being used?**
A: `claude-haiku-4-5-20251001` (cheapest/fastest Claude model). Can be changed in Settings.

**Q: What does "rag_indexed" mean in the database?**
A: 1 = this email has been saved to ChromaDB. 0 = not yet. After backfill, all 3 existing emails should show rag_indexed=1.

**Q: Why does the inbox show "0 new emails fetched"?**
A: The fetcher uses IMAP UIDs. Once it has seen all emails, "new" means only emails that arrive AFTER the last sync. This is normal — not a bug.

**Q: What is test_mode?**
A: When ON (red toggle in Settings), the "Approve" action writes the draft text to a file on your Mac instead of your real email Drafts folder. This is so you can test without accidentally creating real drafts. Turn it OFF when you're ready to use it for real.

---

## Updated TODO Status

- [x] T1 — ChromaDB installed
- [x] T2 — RAG store built (rag/store.py)
- [x] T3 — Migration 011: rag_indexed column
- [x] T4 — analyzer.py built (the brain)
- [x] T5 — Manual sync endpoint: POST /api/inbox/sync
- [x] T5b — Backfill endpoint: POST /api/inbox/backfill
- [x] T6 — Inbox frontend page built
- [ ] T7 — Customer vs supplier tone split (Task 5 above)
- [ ] T8 — Tests (lower priority)
- [ ] T9 — Approve button → IMAP APPEND (Task 4 above — most important)
- [ ] T10 — Show new vs reviewed emails in inbox
- [ ] T11 — Unread badge in nav
- [ ] T6b — Wire auth on inbox routes (Task 6 above)
