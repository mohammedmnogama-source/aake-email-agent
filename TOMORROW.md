# AAKE Email Agent — Read This First (Next Session)

Last updated: **2026-06-14** · Read before starting any session.

---

## 30-second summary

The app is **live on Railway** now (it used to run only on your Mac). All your real
data — company brain, contacts, vendors, emails, quotes — has been copied to the
hosted version. Recent sessions added clickable daily-briefing points, fixed the
blank-briefing bug, and **fixed email syncing** (the app now reads your main Inbox).

**Open the app:** https://aake-frontend-production.up.railway.app
**Password:** `Mohammusta15151`

To make any code change go live: just push to GitHub `main` — Railway redeploys both
parts automatically. (Full deployment details are in `CLAUDE.md` → "Deployment (Railway)".)

---

## What we did in the last sessions (2026-06-13 → 06-14)

1. **Deployed the whole app to Railway** (backend + frontend + a persistent disk for the database).
2. **Migrated all local data to Railway** — 86 company-brain facts, 466 contacts, 19 vendors,
   134 emails, 626 price quotes. The hosted app is now as complete as your Mac version.
3. **Made daily-briefing points clickable** — on the Briefing page, each item under
   "Needs Your Attention" / "Vendors & Quotes" opens the exact emails behind it in the
   Inbox, with all the normal tools (summarize, draft, approve, dismiss). A banner lets
   you jump back to the full inbox.
4. **Fixed the blank-briefing bug** — the page no longer clears when you navigate away;
   it stays until you press Refresh. (Cause: a backend route collision, now fixed.)
5. **Fixed email syncing (06-14)** — the app was only watching a side folder ("AI Agent")
   but your emails arrive in the **main Inbox**, so it kept saying "no new emails." Switched
   it to watch `INBOX` directly. First sync of a folder now only pulls the **last 2 days**
   (so it doesn't drag in years of history), then tracks new mail from there. Your recent
   emails (UPS quote, EXTERNAL RFQ) are now in the app.
6. **Migrated the RAG "filing cabinet" (ChromaDB) to the cloud (06-17)** — the email
   migration had only copied the SQLite database, so the cloud's vector store was empty
   (RAG ran but found nothing). Uploaded the local `chroma_db` (via a `chroma_import.tar.gz`
   + startup hook, same pattern as the DB). Cloud now has 443 past emails + 210 sent emails
   indexed. RAG is now actually personalizing drafts. Confirmed "Learn" is additive/safe —
   it skips already-indexed emails, never deletes.
7. Fixed deploy blockers along the way: fresh-DB migration crash, a Next.js security
   bump, and seeding the dashboard password on the hosted DB.

---

## ✅ Quick test to do first (5 min) — confirm recent work

1. **Email sync:** open the Inbox → click **Sync**. Your newest real emails should appear
   at the top (newsletters/spam included — the AI tags them, you Dismiss what you don't want).
2. **Briefing:** open `/briefing` → click **Refresh** → click a point like "RFQ for ASUS
   and NVIDIA" → it opens just those emails. Click **Briefing** in the nav to return → it
   should **stay** (not go blank).

If a briefing point is NOT clickable, it didn't get tagged with email IDs — tell Claude.

---

## 🔴 Pending tasks (priority order)

| # | Task | Why | Effort |
|---|------|-----|--------|
| 1 | **Make the GitHub repo PRIVATE** | `mohammedmnogama-source/aake-email-agent` is currently **public**. Your code is visible to anyone. (Your passwords are NOT in it — they're gitignored — but the code shouldn't be public.) Do it in GitHub → repo → Settings → change visibility to Private. | 2 min (you) |
| 2 | (Optional) `gh auth login` in Terminal | Stops the "GitHub CLI authentication expired" banner that keeps popping. Purely cosmetic — you don't use pull requests. Ignore it if it doesn't bother you. | 2 min (you) |
| 3 | Verify briefing clickability end-to-end | See the quick test above. Confirm every point links to its emails. | 5 min |
| 4 | (Optional) Rename Railway project | `clever-alignment` is an auto-generated name. Could rename to `aake-agent` in the Railway UI for clarity. | 2 min |

Nothing is broken. These are housekeeping / nice-to-haves.

---

## Ideas / possible future work (not committed — decide later)

- **Spam/newsletter filter** — now that the app watches the whole Inbox, it also pulls in
  newsletters/spam (the AI tags them "spam" and you Dismiss them). If it gets noisy, we can
  auto-skip senders/domains (there's already a `manually_handled_patterns` table for this).
- Make the **Priorities** list on the briefing clickable too (right now only Attention & Vendors link to emails).
- Email/push notification when an important email arrives (instead of checking manually).
- Better thread grouping for the "Summarize Thread" feature.
- Anything from the older roadmap in `AUTOMATION_PLAN.md`.

---

## How things run now (so you're not confused)

- **Production = Railway** (the URLs above). This is what you and your friend use. Always up to date with `main`.
- **Local (your Mac)** = only for development/testing. Start it with the two commands below.
  It is NOT needed for normal use anymore.

**Run locally (only if developing):**
```bash
# Terminal 1 — backend
cd /Users/mohammedmustafa/Desktop/cLaude/email-agent
/opt/anaconda3/bin/python -m uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
cd /Users/mohammedmustafa/Desktop/cLaude/email-agent/frontend
npm run dev
```
Then open `http://localhost:3000`. (Note: the Python with all dependencies is
`/opt/anaconda3/bin/python`, not the default `python3`.)

---

## Hard rules that never change

1. **No smtplib** — drafts saved via IMAP APPEND only.
2. **Sent folder is read-only.**
3. **PII redacted before every Claude call.**
4. **Nothing auto-sends** — you always review and approve.
5. **Never edit an applied migration file** — add a new numbered `.sql`.
6. **Never touch the ERP project** (`/Users/mohammedmustafa/Desktop/cLaude/EXP/MY ERP/frontend`).

---

*(The old detailed file-by-file reference that used to be here is preserved in
`AAKE_EMAIL_AGENT_CONTEXT.md` and `CLAUDE.md`. This file is the short "what's the
state and what's next" brief.)*
