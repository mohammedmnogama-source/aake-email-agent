"""
RAG store — the email "filing cabinet".

Four things this file does:
  1. init()              — opens (or creates) the ChromaDB database on disk
  2. index_email()       — saves one email as a searchable vector
  3. query_similar()     — given a new email, find the 3 most similar past ones
  4. backfill_*()        — one-time jobs to index emails that were saved before
                           ChromaDB was added

PII rule: redact() is always called INSIDE this file before anything is stored.
Callers must never pre-redact — let this file handle it so the rule can't be skipped.
"""

import os
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from backend.ai.redactor import redact

# ChromaDB will save its data here, next to agent.db
_CHROMA_PATH = os.environ.get("CHROMA_PATH", "data/chroma_db")

# Name of the collection (like a table) inside ChromaDB
_COLLECTION_NAME = "emails"

_client = None
_collection = None


def _get_collection():
    """
    Returns the ChromaDB collection, creating it if it doesn't exist yet.
    Uses the default embedding model (all-MiniLM-L6-v2, ~23MB, runs on your Mac).
    """
    global _client, _collection
    if _collection is not None:
        return _collection

    Path(_CHROMA_PATH).mkdir(parents=True, exist_ok=True)

    _client = chromadb.PersistentClient(path=_CHROMA_PATH)

    # Default embedding function — downloads model on first run (~23MB, one time only)
    ef = embedding_functions.DefaultEmbeddingFunction()

    _collection = _client.get_or_create_collection(
        name=_COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},  # cosine = best for text similarity
    )
    return _collection


def index_email(
    email_id: int,
    body_text: str,
    subject: str = "",
    from_address: str = "",
    tone_type: str = "general",  # "customer", "supplier", or "general"
    action_taken: str = "",       # what happened to this email (e.g. "draft_reply")
) -> None:
    """
    Saves one email into ChromaDB so it can be found by future RAG queries.

    - Redacts PII before storing (Civil IDs, IBANs, card numbers, etc.)
    - Uses email_id as the unique key — safe to call twice, second call is ignored
    """
    col = _get_collection()

    # Check if already indexed — ChromaDB raises if you add a duplicate ID
    existing = col.get(ids=[str(email_id)])
    if existing["ids"]:
        return  # already in the cabinet, skip

    # Always redact before storing — PII must never go into ChromaDB
    clean_body, _ = redact(body_text or "")
    clean_subject, _ = redact(subject or "")

    # The text ChromaDB will embed (convert to numbers)
    document = f"Subject: {clean_subject}\n\n{clean_body}".strip()

    if not document:
        return  # nothing to index

    col.add(
        ids=[str(email_id)],
        documents=[document],
        metadatas=[{
            "email_id": email_id,
            "from_address": from_address,
            "tone_type": tone_type,
            "action_taken": action_taken,
            "subject": clean_subject,
        }],
    )


def query_similar(body_text: str, subject: str = "", n: int = 3) -> list[dict]:
    """
    Given a new email's body text, find the n most similar past emails.

    Returns a list of dicts like:
      [
        {
          "email_id": 42,
          "subject": "Re: Cisco quote",
          "document": "redacted body preview...",
          "action_taken": "draft_reply",
          "tone_type": "supplier",
          "distance": 0.12,   # lower = more similar
        },
        ...
      ]

    Returns [] if ChromaDB is empty (e.g. first run before any indexing).
    """
    col = _get_collection()

    # Don't query if the collection is empty
    if col.count() == 0:
        return []

    # Redact the query text too — we're sending it to the local model, but good habit
    clean_body, _ = redact(body_text or "")
    clean_subject, _ = redact(subject or "")
    query_text = f"Subject: {clean_subject}\n\n{clean_body}".strip()

    if not query_text:
        return []

    # Ask ChromaDB for the n most similar past emails
    results = col.query(
        query_texts=[query_text],
        n_results=min(n, col.count()),  # can't ask for more than what exists
        include=["documents", "metadatas", "distances"],
    )

    similar = []
    for i, doc_id in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i]
        similar.append({
            "email_id": meta.get("email_id"),
            "subject": meta.get("subject", ""),
            "document": results["documents"][0][i],
            "action_taken": meta.get("action_taken", ""),
            "tone_type": meta.get("tone_type", "general"),
            "distance": results["distances"][0][i],
        })

    return similar


def backfill_existing_emails(conn) -> int:
    """
    One-time job: index all emails already in the SQLite database that
    haven't been indexed to ChromaDB yet (rag_indexed = 0).

    Returns the number of emails indexed.
    """
    rows = conn.execute(
        "SELECT id, subject, body_text, from_address "
        "FROM emails "
        "WHERE rag_indexed = 0 AND body_text IS NOT NULL "
        "ORDER BY id"
    ).fetchall()

    count = 0
    for row in rows:
        try:
            index_email(
                email_id=row["id"],
                body_text=row["body_text"] or "",
                subject=row["subject"] or "",
                from_address=row["from_address"] or "",
            )
            conn.execute(
                "UPDATE emails SET rag_indexed = 1 WHERE id = ?", (row["id"],)
            )
            count += 1
        except Exception as e:
            print(f"[rag] Failed to index email {row['id']}: {e}")

    if count:
        conn.commit()
        print(f"[rag] Backfilled {count} existing email(s) into ChromaDB")

    return count


def backfill_sent_folder(conn) -> int:
    """
    One-time job: fetch Mo's sent emails from IMAP (read-only) and index them.
    This gives ChromaDB examples of how Mo actually writes, before any new
    emails arrive.

    Reuses the same read-only IMAP pattern from style_learner.py.
    Returns the number of sent emails indexed.
    """
    from imap_tools import A
    from backend.email.fetcher import _strip_html
    from backend.email.imap_client import get_mailbox

    sent_folder = _find_sent_folder(conn)
    if not sent_folder:
        print("[rag] Could not find Sent folder — skipping sent backfill")
        return 0

    count = 0
    try:
        with get_mailbox() as mb:
            mb.folder.set(sent_folder, readonly=True)
            messages = sorted(
                mb.fetch(A(all=True), mark_seen=False, bulk=True),
                key=lambda m: int(m.uid),
                reverse=True,
            )[:100]  # index up to 100 sent emails

        for msg in messages:
            body = msg.text or _strip_html(msg.html or "")
            if not body.strip():
                continue
            # Use a negative ID space for sent emails so they don't clash with inbox IDs
            # Sent email "virtual ID" = -(imap_uid) so it's unique in ChromaDB
            virtual_id = -(int(msg.uid))
            try:
                index_email(
                    email_id=virtual_id,
                    body_text=body,
                    subject=msg.subject or "",
                    from_address=str(msg.from_),
                    tone_type="sent",
                    action_taken="sent_by_mo",
                )
                count += 1
            except Exception as e:
                print(f"[rag] Failed to index sent email uid={msg.uid}: {e}")

    except Exception as e:
        print(f"[rag] Sent folder backfill error: {e}")

    if count:
        print(f"[rag] Indexed {count} sent email(s) from IMAP into ChromaDB")

    return count


def _find_sent_folder(conn) -> str | None:
    """
    Looks for the Sent folder name in settings, or tries common names.
    Reuses the same logic as style_learner.py.
    """
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'sent_folder'"
    ).fetchone()
    if row and row["value"]:
        return row["value"]

    # Common cPanel sent folder names
    for candidate in ("INBOX.Sent", "Sent", "INBOX.Sent Items", "Sent Items"):
        try:
            from backend.email.imap_client import get_mailbox
            with get_mailbox() as mb:
                folders = [f.name for f in mb.folder.list()]
                if candidate in folders:
                    return candidate
        except Exception:
            pass

    return None
