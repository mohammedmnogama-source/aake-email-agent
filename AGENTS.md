# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What This Is

A deal management system for AAKE Kuwait (IT reseller — Cisco, Fortinet, HP, Microsoft). Mo creates deals from customer inquiries (paste email or manual form), tracks supplier requests and quotes, and manages the full lifecycle through to purchase orders. AI extracts deal info from emails, suggests next steps, and drafts supplier request emails. **Nothing ever auto-sends.**

## Commands

```bash
# First-time setup (IMAP config, password hash, vendor seed)
python scripts/setup.py

# Run the API server
uvicorn backend.main:app --reload --port 8000

# Run tests
pip install pytest httpx
pytest backend/tests/
pytest tests/test_redaction.py          # standalone redaction tests

# Lint
ruff check backend/
ruff check backend/ --fix

# Manually trigger email fetch + analysis
python -m backend.ai.analyzer

# Apply DB migrations (auto-runs on server start, or manually)
python -c "from backend.database.connection import init_db; from backend.config import settings; init_db(settings.database_path)"
```

## Architecture

### Request Flow

```
IMAP (cPanel, port 993)
  → backend/email/fetcher.py          UID-based incremental fetch → emails table (status=pending)
  → backend/ai/analyzer.py            redact PII → call Codex → store ai_suggestions
  → FastAPI /api/inbox                Mo reviews in dashboard
  → /api/decisions/{id}/approve       runs action handler → IMAP APPEND draft (or test file)
```

The scheduler (`backend/scheduler.py`, APScheduler) runs `fetch_new_emails()` + `analyze_pending()` every N minutes (configurable via `poll_interval_min` setting).

### AI Pipeline

`backend/ai/analyzer.py` is the orchestrator:
1. Checks `manually_handled_patterns` — skips API call if sender domain is known
2. Calls `redact_email()` — strips Civil IDs, IBANs, card numbers, passwords, API keys from body before sending to Codex
3. Calls `call_ai()` in `backend/ai/gemini_client.py` (despite the filename, uses Anthropic Codex)
4. Every `call_ai()` logs to `api_audit_log` (sha256 hash + sizes, never content)
5. If Codex returns `needs_clarification=True`, email goes to `clarification_pending` status — Mo answers via `/api/clarifications/{id}/answer`, max 3 rounds
6. Normal result stored in `ai_suggestions`, email moves to `decided`

Model is stored in the `settings` table (`ai_model` key), defaulting to `Codex-haiku-4-5-20251001`. Temperature is 0.2.

### Database

SQLite WAL mode, single file at `data/agent.db`. Migrations in `backend/database/migrations/` run automatically on startup — never edit applied migration files, always add a new numbered `.sql` file.

`get_connection()` must be called after `init_db()` (done by FastAPI lifespan). All repos accept a `conn` parameter — callers own the connection lifecycle.

Key tables: `emails`, `ai_suggestions`, `decisions`, `actions_taken`, `leads`, `vendors`, `clarification_responses`, `writing_style`, `style_examples`, `api_audit_log`, `manually_handled_patterns`, `settings`.

### Test Mode

When `settings.test_mode = '1'` (default), approvals write draft text to `data/test_drafts/<timestamp>_<email_id>.txt` instead of appending to the real IMAP Drafts folder. Toggle via `PATCH /api/settings/test_mode`.

### Auth

Single-user bcrypt password stored in `settings.dashboard_password`. Login returns a JWT (`PyJWT`, `SECRET_KEY` from `.env`). The `require_auth` dependency is in `backend/middleware/auth.py` — routers currently don't enforce it (Step 5 wiring pending).

### Style Learner

`backend/email/style_learner.py` reads the last 50 Sent emails read-only, redacts them, and calls Codex to extract a writing style profile (greeting, sign-off, formality, etc.). First run is always a dry-run — Mo must confirm via `POST /api/style/confirm` before the profile is saved and injected into draft prompts.

### Clarification Flow

When Codex can't determine the right action, it returns `needs_clarification=True` with a question and options. The email status becomes `clarification_pending`. Mo answers via the dashboard, which POSTs to `/api/clarifications/{suggestion_id}/answer`. After 3 unanswered rounds, `force_definitive=True` is passed to the prompt and Codex must return a result.

## Key Constraints

- **No smtplib anywhere** — drafts go via IMAP APPEND only (`backend/email/draft_saver.py`)
- **Sent folder access is read-only** — `mb.folder.set(folder, readonly=True)` enforced in style_learner
- **PII redaction runs before every Codex call** — never send raw `body_text` to `call_ai()`
- **`call_ai()` is in `gemini_client.py`** — the filename is legacy; it uses `anthropic.Anthropic`
- **cPanel IMAP quirk** — all folders are prefixed `INBOX.` (e.g. `INBOX.AI Agent`, `INBOX.Drafts`)
- **Fresh connection per request** — cPanel aggressively times out idle IMAP connections

## Environment Variables (`.env`)

```
EMAIL_ADDRESS, EMAIL_PASSWORD       cPanel IMAP credentials
ANTHROPIC_API_KEY                   Codex API key (sk-ant-...)
SECRET_KEY                          JWT signing secret (32+ random chars)
DATABASE_PATH                       defaults to data/agent.db
```

## Known Mistakes — Error Log

These bugs cost hours. Do not repeat them.

### 1. SQLite FK auto-rename (CRITICAL)
When you run `ALTER TABLE X RENAME TO Y`, SQLite 3.26+ silently rewrites all FK references
in OTHER tables to point to Y. So if you rename `emails` to `emails_v7`, then `api_audit_log`
suddenly has `REFERENCES emails_v7` even though you never touched it.
**Rule:** Always use `PRAGMA foreign_keys = OFF` around table rebuilds. After any rename,
run `SELECT sql FROM sqlite_master WHERE type='table'` to verify all FKs are correct.

### 2. Migration table ordering
If table B has a FK to table A, create A before B in the same migration file.
In migration 008, `input_batches` was defined after `emails` which referenced it →
`no such table: input_batches` crash.

### 3. Migration partial runs
If a migration fails halfway, the migration runner won't retry (file not in `_migrations`),
but the partial tables exist. The DB is in a broken half-applied state.
**Rule:** Always test migrations on a fresh DB first. Wrap multi-step migrations in a
transaction where possible.

### 4. Pydantic enum validation
If Codex returns a string value not defined in a Pydantic `Enum`, it throws `ValidationError`
at runtime. Always check that every value Codex might return is listed in the enum before
shipping. Past example: `create_rfq` was returned by Codex but missing from `SuggestedAction`.

### 5. PDF stacked text layers
Some PDFs embed multiple identical text layers. pdfplumber returns every character 4×
(e.g. `FFFFrrrr` instead of `Fr`). Fix is in `backend/email/pdf_extractor.py`:
`re.sub(r'(.)\1{3,}', r'\1', text)`. Do not remove this line.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
