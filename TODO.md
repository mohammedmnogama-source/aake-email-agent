# AAKE Email Agent — Phase 2 To-Do List

Last updated: 2026-06-08

---

## 🔴 Priority 1 — Core (must work before anything else)

- [x] T1 — Install ChromaDB (requirements.txt)
- [x] T2 — Build RAG store (backend/rag/store.py) — the "filing cabinet"
- [x] T3 — Migration 011: rag_indexed column on emails table
- [x] T4 — Build analyzer.py — the brain (fetch → RAG → Claude → draft reply)
- [x] T5 — Manual sync endpoint: POST /api/inbox/sync
- [x] T5b — Backfill endpoint: POST /api/inbox/backfill
         Reads ALL sent emails from IMAP + existing DB emails → indexes to ChromaDB
         This is how the agent "learns" from your email history
- [x] T6 — Build frontend Inbox page (localhost:3000/inbox)
         Shows: email list, AI summary, suggested action, draft reply
         Has: Sync Inbox button, Backfill button

---

## 🟡 Priority 2 — Smart replies (do after Priority 1 works)

- [ ] T7 — Customer vs Supplier tone split
         Migration 012: tone_type column on writing_style table
         Extend style_learner.py to save two profiles (customer / supplier)
         Update _build_style_block() to pick the right tone per email
- [ ] T8 — Tests: cover all new code paths in analyzer.py + rag/store.py

---

## 🟢 Priority 3 — Polish (do when the core is solid)

- [ ] T9 — Frontend: approve / reject buttons on draft replies
         When approved → save to IMAP Drafts via draft_saver.py
- [ ] T10 — Frontend: show which emails are "new" vs "reviewed"
- [ ] T11 — Frontend: Inbox badge in nav showing unread count
- [ ] T12 — Style paste page improvements (paste your sent emails to learn your tone)

---

## ✅ Already working (Phase 1 — built before Phase 2)

- Style learning: POST /api/style/paste → learns your writing style from pasted emails
- Style confirm: POST /api/style/confirm → activates the style profile
- Deal management: create deals, track RFQs, supplier requests, quotes, POs
- Draft saving: IMAP APPEND only (no smtplib — ever)
- PII redaction: runs before every Claude call and before every ChromaDB index

---

## 🚫 Out of scope (decided not to build these)

- Auto-polling every N minutes (removed — you trigger manually instead)
- Ollama on Windows PC (Claude API is better for structured JSON)
- Auto-sending emails (hard constraint — never)
- PDF attachments in RAG (email bodies only for now)
