# Phase 2 — Email Agent → ERP CRM Integration Plan

> Written 2026-06-18 after a full audit of the ERP CRM schema and the email
> agent. Read this BEFORE starting any Phase 2 implementation.
> The companion constraints in `email-agent/CLAUDE.md` and
> `EXP/MY ERP/frontend/CLAUDE.md` still apply to everything here.

---

## Deployment context

- **ERP / CRM frontend** → hosted on **Vercel** (Next.js).
- **ERP database / system of record** → **Supabase** (Postgres).
- **Email Agent** → hosted separately on **Railway** (FastAPI + SQLite).
- **Supabase/ERP is the single source of truth** for all CRM data.
- The **Email Agent is only the AI brain + staging/scratchpad.** It must NOT
  write real deals/tasks/contacts into its own SQLite as the system of record.
- After **human approval**, the Email Agent calls **protected ERP HTTP APIs**
  (shared-secret) to create/update the real CRM records in Supabase.

### Authentication (shared secret — NOT CORS)
Every Email-Agent → ERP write endpoint requires a shared secret. CORS is not auth.

- ERP / Vercel env var: `EMAIL_AGENT_SHARED_SECRET`
- Railway / Email Agent env var (same value): `ERP_SHARED_SECRET`
- Request header the agent must send: `X-AAKE-Agent-Secret: <secret>`
- Missing/wrong secret → `401 { ok: false, error: "Unauthorized" }`
- Fails closed: if the env var is unset on the ERP, all requests are rejected.

Helper that enforces it: `src/lib/agent-auth.ts` (`checkAgentSecret`, `AGENT_CORS`).
`POST /api/rfqs` is used only by the Email Agent (no public website/form calls it),
so it is protected with the same secret directly — no separate `/api/agent/rfqs` needed.

### Response shape (all endpoints)
- Success: `{ ok: true, id, reference }` (`reference` is null where the table has none;
  upsert/duplicate hits also include `duplicate: true`).
- Failure: `{ ok: false, error }` with a 4xx/5xx status.

## The one rule that governs all of Phase 2

**The ERP (Next.js + Supabase Postgres) is the single system of record for the
CRM. The email agent's SQLite is a staging area / scratchpad only.**

The audit found the email agent quietly built its OWN parallel CRM inside SQLite
(`deals`, `deal_items`, `quotations`, `rfqs`, `supplier_requests`,
`suggested_tasks`, `leads`). That is the duplication we are deliberately NOT
building on. Those SQLite tables stay as "what the AI proposes." When Mohammed
approves a proposal, the **applier** pushes it into the real ERP over HTTP and
records the returned ERP id back on the SQLite row so it is never applied twice.

Hard "do nots" for this phase:
- Do NOT build a second CRM.
- Do NOT treat the email agent's SQLite `deals`/`quotations` as real.
- Do NOT build email-extraction logic inside the ERP. Extraction lives in the
  agent; the ERP only exposes thin write endpoints.
- Do NOT add Notion, Calendar, GraphRAG, OCR, or auto-send in this phase.
- Do NOT create new CRM tables in the ERP unless strictly required.

---

## The data flow

```
pending_extraction (agent SQLite)     applier (agent)         ERP CRM (Supabase = source of truth)
─────────────────────────────────     ───────────────         ──────────────────────────────────
suggested_tasks rows (approved=0)
  task_type: create_lead       ──HTTP POST──▶ POST /api/leads     → leads
  task_type: create_rfq        ──HTTP POST──▶ POST /api/rfqs      → rfqs        (ALREADY EXISTS)
  task_type: create_deal       ──HTTP POST──▶ POST /api/deals     → quotations
  task_type: create_task       ──HTTP POST──▶ POST /api/tasks     → tasks
  task_type: log_email_to_deal ──HTTP POST──▶ POST /api/deals/log → deal_activities + (optional) tasks
  contact details              ──HTTP POST──▶ POST /api/contacts  → parties + contacts
```

1. AI extracts → rows land in `suggested_tasks` (`approved = 0`).
2. Mohammed approves in the inbox.
3. The applier calls the matching ERP endpoint.
4. On `{ ok: true }`, the applier stamps `executed_at` and stores the returned
   ERP `id` / `reference` back on the SQLite row (idempotency guard).

Why HTTP and not a direct DB write: the agent runs on Railway with its own
SQLite; it cannot reach the ERP's Supabase. The ERP rule (`CLAUDE.md`) is that
the agent may CALL the ERP's HTTP API but never touch ERP code.

---

## ERP-side changes (the only work to prepare before the agent build)

All new endpoints copy the EXACT pattern of the existing
`src/app/api/rfqs/route.ts`:
- `OPTIONS` handler + `CORS` headers (origin = `process.env.EMAIL_AGENT_ORIGIN`)
- `createServerSupabaseClient()` (service role)
- duplicate-check FIRST
- atomic `next_reference` RPC for any reference number
- return `{ ok: true, id, reference }`, or `{ error }` with a 4xx/5xx
- use existing tables and existing status/stage enums only

### New endpoints

| Endpoint | Writes to | Duplicate check | Returns |
|----------|-----------|-----------------|---------|
| `POST /api/contacts` | `parties` (+ `contacts`) | `parties` by `ilike name`, type=customer → reuse if found | `{ ok, id, reference: display_id }` |
| `POST /api/leads` | `leads` | by `email` (or first+last+company) in `leads` | `{ ok, id, reference: null }` |
| `POST /api/deals` | `quotations` | by `name`/`ext_ref` match (mirror addDeal) | `{ ok, id, reference }` |
| `POST /api/tasks` | `tasks` | by identical `title` + open status (light) | `{ ok, id, reference: null }` |
| `POST /api/deals/log` | `deal_activities` (+ optional `tasks`) | none (append-only log) | `{ ok, id }` |
| `POST /api/rfqs` | `rfqs` | EXISTS — same subject last 30 days | unchanged |

Endpoint bodies (proposed):

```jsonc
// POST /api/contacts
{ "name": "required", "company": "optional", "email": "optional",
  "phone": "optional", "contact_person": "optional", "country": "Kuwait" }

// POST /api/leads
{ "first_name": "optional", "last_name": "optional", "company": "optional",
  "email": "optional", "phone": "optional", "lead_source": "email",
  "notes": "optional" }   // status defaults to 'new'

// POST /api/deals
{ "name": "required (deal title)", "customer_name": "optional lookup",
  "total": 0, "notes": "optional", "source": "email_agent" }
// status defaults to 'draft'; reference from next_reference('QT')

// POST /api/tasks
{ "title": "required", "description": "optional",
  "priority": "low|medium|high|urgent (default medium)",
  "due_date": "YYYY-MM-DD optional",
  "related_type": "quotation|rfq|null", "related_id": "uuid|null",
  "email_id": "agent email id, optional" }
// status defaults to 'open'

// POST /api/deals/log   (mirrors the existing logEmailToDeal server action)
{ "deal_id": "uuid required", "kind": "deal|rfq",
  "situation": "what happened (required)",
  "email_subject": "optional", "email_direction": "sent|received",
  "email_id": "agent email id, optional",
  "next_action_title": "optional task", "next_action_due": "YYYY-MM-DD optional" }
```

### Enum / value rules the endpoints MUST follow
- `tasks.status`: `open | in_progress | done | cancelled` (default `open`)
- `tasks.priority`: `low | medium | high | urgent` (default `medium`)
- `quotations.status`: `draft | sent | accepted | rejected | expired`
  (deals from the agent start at `draft`)
- `leads.status`: `new | contacted | qualified | converted | lost` (default `new`)
- `rfqs.status`: `new | in_progress | quoted | won | lost | not_interested`
- `deal_activities` is immutable (INSERT only) — never update/delete

### Small schema changes (only if needed for the email link)
Run in Supabase SQL editor:
```sql
-- Link tasks and activity-log rows back to the source email (nullable, safe)
ALTER TABLE tasks           ADD COLUMN IF NOT EXISTS email_id TEXT;
ALTER TABLE deal_activities ADD COLUMN IF NOT EXISTS email_id TEXT;

-- Mark AI-created deals distinctly on the pipeline (4th source value)
-- quotations.source today allows: 'mohammed' | 'manager' | 'app'
ALTER TABLE quotations DROP CONSTRAINT IF EXISTS quotations_source_check;
ALTER TABLE quotations ADD  CONSTRAINT quotations_source_check
  CHECK (source IN ('mohammed','manager','app','email_agent'));
```
No new CRM tables. `email_id` is plain TEXT (the agent's email id), nullable, so
existing rows and the existing UI are untouched.

### Gotchas the implementer must honor (from ERP CLAUDE.md)
- `parties` `display_id` trigger is broken → in `/api/contacts`, set
  `display_id` manually and bump `party_counters` (same workaround as SQL inserts).
- `quotations` has TWO FKs to `parties` → any join must use
  `parties:customer_id(name)`.
- `types.ts` is incomplete → insert with `as never` for `rfqs`, `deal_activities`,
  `leads` extras, etc.
- Existing `/api/rfqs` has CORS but no bearer auth — mirror that for consistency
  (tighten all of them together later if desired).

---

## What is explicitly reused (no new build)
- ERP tables: `quotations`, `parties`, `contacts`, `leads`, `tasks`, `rfqs`,
  `deal_activities`.
- The existing `logEmailToDeal` logic in `quotations/actions.ts` — `/api/deals/log`
  is just an HTTP wrapper around the same behavior (log + optional task).
- The agent's `suggested_tasks` table — it already has `payload` (JSON),
  `approved`, `executed_at`, `depends_on_task_id`: a ready-made staging layer.

## Build order
1. ERP schema migration (the SQL above).
2. ERP endpoints: `/api/contacts`, `/api/leads`, `/api/deals`, `/api/tasks`,
   `/api/deals/log` (copy `/api/rfqs/route.ts`).
3. Then (separate agent session) wire the applier in the email agent to call
   them on approve, and write the returned id back to `suggested_tasks`.
