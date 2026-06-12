# AAKE Email Agent — Full Automation Plan

> Written 2026-06-12 by Fable (planning session) for execution by a future
> Claude session. Mo approved every decision in this plan explicitly.
> Read CLAUDE.md first — its constraints apply to everything here.

## Vision (Mo's words, condensed)

Click an email → AI summary + AI draft appear instantly. Mo types rough words
→ AI turns them into a proper draft in his voice. The system learns his
business deeply, chases follow-ups, briefs him every morning, files things
into the ERP, and earns the right to finish drafts by itself — so Mo spends
his time growing the business, not running it.

## Decisions Mo locked (do NOT re-ask, do NOT change)

| Decision | Choice |
|---|---|
| Auto-send | **Never.** App must stay physically unable to send (no smtplib — constitutional rule). Trusted categories get finished drafts auto-placed in the real IMAP Drafts folder instead. |
| Trust model | Per-category "earn trust": a category becomes trusted after a streak of approvals **without edits**. Any edited approval resets the streak. Mo can revoke trust anytime. |
| Database | Keep SQLite on localhost for now. Migrate to **Supabase Postgres at Railway deploy time** (separate future session — Phase 4). |
| Automations wanted (all) | Follow-up chaser, Morning briefing, ERP auto-create, Price list brain |
| AI knowledge sources | Full Sent-folder history, an editable Business Facts page, deals+customer history from this app's DB. **No Zoho integration** (skipped deliberately). |
| Morning briefing | Dashboard "Today" page (no email delivery) |
| Deploy target | Railway (later session). Localhost until then. |

## Current state (audited 2026-06-12)

Working: IMAP fetch → redact → Claude analysis → suggestions (120/120 emails
processed), RAG with 429 indexed emails in ChromaDB (`emails` collection),
style profile learned + active, 15-min scheduler, Outlook-style two-panel
inbox UI, compose + re-draft endpoints, deals/customers/vendors/prices pages.

Broken / weak:
- `approved_drafts` table + ChromaDB collection exist but have **0 rows** —
  the learning loop is built but has never been fed (Mo wasn't using Approve)
- Auth middleware exists (`backend/middleware/auth.py`) but **no router
  enforces it**
- `test_mode = 1` — approvals write to `data/test_drafts/` files, not real Drafts
- Migration files **001, 004, 007, 008, 009 are lost** (iCloud incident
  2026-06-12; live DB is fine — they were applied long ago). The live schema
  is the source of truth, recover schema via `sqlite3 data/agent.db .schema`
- Frontend hardcodes `const BASE = 'http://localhost:8000'` in every page
- Dead cruft: `backend/email/smtp_client.py` (imported by nothing — keep it
  that way or remove WITH Mo's confirmation), `backend/rag/store 2.py`
  (iCloud duplicate), `*-broken-icloud` leftovers (Mo trashes via Finder),
  legacy `gemini_model` settings row

---

## Phase 0 — Repairs & safety ✅ DONE (2026-06-12)

0.1 **Regenerate lost migrations** so a fresh DB can be built (needed for
    Supabase later). Dump live schema: `sqlite3 data/agent.db .schema` and
    write it as `backend/database/migrations/000_baseline_rebuilt.sql` with a
    guard comment explaining it replaces lost 001/004/007/008/009 on fresh
    installs only. Do NOT run anything against the live DB — it's already
    migrated. Test on a throwaway DB file.

0.2 **Enforce auth.** Add `Depends(require_auth)` to every router except
    `/api/auth/login` (and `/docs` can stay open on localhost). The frontend
    already stores `aake_token` and sends `Authorization: Bearer` — verify
    login page flow end-to-end afterward.

0.3 **Env-based API URL in frontend.** Replace hardcoded `BASE` with
    `process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'` in ONE
    shared module (e.g. `frontend/lib/api.ts`) and import it everywhere.
    This unblocks Railway later without touching pages again.

0.4 Delete legacy `gemini_model` settings row (SQL UPDATE is fine; it's one
    row of config, not a file).

## Phase 1 — The Learning Engine ✅ DONE (2026-06-12)

1.1 **Index ALL sent emails** (new ChromaDB collection `sent_history`).
    Extend the backfill flow (`style_learner.py` / inbox backfill endpoint):
    read the entire `INBOX.Sent` folder read-only, paginated (500/batch),
    redact PII, embed locally (Chroma's default local embedder — free, no
    API cost), store metadata: recipient domain, subject, date. Track
    progress in a `sent_sync` settings row so re-runs are incremental.
    UI: the existing "🧠 Learn" button shows live progress + total indexed.

1.2 **Business Facts page.** New table `business_facts(id, fact, category,
    updated_at)` + a section on the Settings page where Mo writes plain-
    English facts ("We resell Cisco/Fortinet/HP/Microsoft", "Standard
    delivery 4–6 weeks", "Never discount below X without approval", payment
    terms, key customers). ALL facts are injected into the analyzer system
    prompt and compose/redraft prompts. Keep under ~1500 tokens; warn in UI
    when exceeded.

1.3 **Deal/customer context injection.** In `analyzer.py` before drafting:
    look up sender address/domain in `customers` + open `deals` (and their
    supplier request status). Add a "WHAT WE KNOW ABOUT THIS SENDER" block to
    the user message: open deals, last quote sent, days since last contact.
    Same lookup for the redraft endpoint.

1.4 **Draft sources upgrade.** When drafting, RAG queries should hit, in
    priority order: `approved_drafts` (what Mo actually approved) →
    `sent_history` (how Mo talks) → `emails` (similar inquiries). The
    analyzer already queries approved_drafts; add sent_history.

1.5 **Learning progress widget** on the Today page (Phase 3 builds the page;
    until then put it atop the inbox): approvals total, % approved without
    edits per category, trust streaks. Makes the learning visible so Mo
    actually feeds it.

## Phase 2 — Trust system (auto-finish into Drafts) ✅ DONE (2026-06-12)

2.1 New table `category_trust(category TEXT PRIMARY KEY, streak INT,
    trusted INT, trusted_at TEXT, total_approved INT, total_edited INT)`.

2.2 On every approve (`_save_approved_draft` already computes `was_edited`):
    unedited → streak+1; edited → streak=0. At streak ≥ 10 (configurable
    settings row `trust_threshold`) set trusted=1.

2.3 When analyzing a NEW email whose category is trusted AND suggestion has
    a draft AND `needs_clarification` is false: automatically run the same
    code path as approve (IMAP APPEND to real Drafts; respects test_mode),
    record in `actions_taken` with `auto=1`, and mark the suggestion
    `auto_finished=1`.

2.4 **Hard safety rails (never relax):**
    - Drafts containing prices/amounts/totals are NEVER auto-finished,
      regardless of trust (regex scan for currency/numbers before APPEND)
    - Categories `vendor_quote_request`, `internal`, `spam` can never earn
      trust (no drafts should exist for them anyway)
    - Follow-up chaser drafts (Phase 3) never auto-finish
    - App remains physically unable to SMTP-send. Auto-finish = Drafts only.

2.5 UI: "Auto-finished" filter pill in inbox + per-category trust panel in
    Settings with streak progress and a one-click **Revoke** button.
    Today page shows "While you were away: N drafts auto-finished" list.

## Phase 3 — Automations

3.1 ✅ DONE (2026-06-12) **Follow-up chaser.** Daily scheduler job: find outbound threads (from
    sent_history + emails tables) where WE sent last message ≥ N days ago
    (default 4, settings row) tied to a lead/customer_inquiry/open deal, and
    no reply since. For each, generate a short polite follow-up draft →
    normal approval queue, flagged `source='followup_chaser'` with its own
    inbox filter pill. Never auto-finished.

3.2 **Morning briefing — Today page.** Make `frontend/app/page.tsx` the
    dashboard: overnight emails by category, drafts waiting for approval,
    auto-finished list, follow-ups suggested, deals with no supplier quote
    in X days, top-3 suggested priorities (one Haiku call, cached per day in
    a `daily_briefing` table so refreshes are free). Learning progress
    widget (1.5) lives here.

3.3 **ERP auto-create.** The one-click RFQ/Lead/Task modals already exist.
    Add the same trust mechanic per ACTION (separate from email categories):
    after 10 unedited one-click creations of a type, offer Mo a toggle to
    auto-create that type (logged to `actions_taken`, shown on Today page).
    ERP rule from CLAUDE.md still applies: this app may CALL the ERP's HTTP
    API, but never touch ERP code. If the ERP needs new endpoints, write a
    prompt doc for Mo to paste into his ERP session.

3.4 **Price list brain.** Vendor emails with .xlsx/.pdf attachments:
    extract rows (openpyxl / pdfplumber — both installed; reuse
    `price_extractor.py` + dedupe logic) into the existing `price_quotes`
    table. Inject "LAST KNOWN PRICES for products mentioned" into drafts for
    matching part numbers, with the never-state-prices-unless-asked rule
    from the system prompt still in force. Prices page gets search by part
    number/vendor showing price history.

## Phase 4 — Deploy (SEPARATE FUTURE SESSION — do not start without Mo)

Railway + Supabase. High-level only (detail it in that session):
- Swap SQLite → Supabase Postgres using the Phase 0.1 baseline schema;
  write a one-time data copy script; repos keep their `conn` interface
- ChromaDB → Railway volume (simplest) — revisit if multi-instance
- Secrets → Railway env vars; tighten CORS to the real frontend URL;
  auth mandatory everywhere; rate-limit login
- Frontend → Railway (or Vercel) with `NEXT_PUBLIC_API_BASE` set
- Scheduler must run in exactly ONE backend instance

## Permanent guardrails (repeat in every session)

1. PII redaction before every Claude call — no exceptions
2. No smtplib anywhere; IMAP APPEND to Drafts is the only outbound path
3. Sent folder strictly read-only
4. Never state prices in a draft unless they were in the original email or
   Mo asked
5. ERP codebase untouchable (`/Users/mohammedmustafa/Desktop/cLaude/EXP/MY ERP/`)
6. Ask Mo before deleting anything; deletions go to ~/.Trash only
7. Model: `claude-haiku-4-5-20251001` for analysis (settings `ai_model`);
   keep temperature 0.2

## Build order for the implementation session

Phase 0 → 1.1 → 1.2 → 1.3+1.4 → 1.5 → 2 (whole) → 3.2 → 3.1 → 3.4 → 3.3.
Test after each step (`pytest backend/tests/`, manual inbox click-through).
Mo should flip `test_mode` off only after Phase 2 ships and he's approved a
few real drafts.
