"""
RAG store for Mo's sent emails — the "how Mo writes" cabinet.

Separate ChromaDB collection from the inbox `emails` collection so
drafts can query Mo's own voice without polluting incoming-email search.

PII rule: redact() is always called before anything is stored.
Callers must never pre-redact — this file handles it.
"""

import threading
import os
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from backend.ai.redactor import redact

_CHROMA_PATH = os.environ.get("CHROMA_PATH", "data/chroma_db")
_COLLECTION_NAME = "sent_history"

_client = None
_collection = None
_init_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Collection accessor
# ---------------------------------------------------------------------------

def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    with _init_lock:
        if _collection is not None:
            return _collection
        Path(_CHROMA_PATH).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=_CHROMA_PATH)
        ef = embedding_functions.DefaultEmbeddingFunction()
        _collection = _client.get_or_create_collection(
            name=_COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def get_count() -> int:
    """Number of sent emails currently indexed."""
    return _get_collection().count()


# ---------------------------------------------------------------------------
# Index / Query
# ---------------------------------------------------------------------------

def index_sent_email(
    uid: int,
    body_text: str,
    subject: str = "",
    recipients: str = "",
    date_str: str = "",
) -> bool:
    """
    Index one sent email. Returns True if newly added, False if already existed.
    IDs are prefixed `sent_<uid>` to avoid clashing with inbox collection IDs.
    """
    col = _get_collection()
    doc_id = f"sent_{uid}"

    if col.get(ids=[doc_id])["ids"]:
        return False  # already indexed

    clean_body, _ = redact(body_text or "")
    clean_subject, _ = redact(subject or "")
    document = f"Subject: {clean_subject}\n\n{clean_body}".strip()

    if not document:
        return False

    # Pull recipient domain from the first address for metadata
    recipient_domain = ""
    if recipients:
        try:
            first = recipients.split(",")[0].strip().strip("<>")
            if "@" in first:
                recipient_domain = first.split("@")[-1].lower()
        except Exception:
            pass

    col.add(
        ids=[doc_id],
        documents=[document],
        metadatas=[{
            "uid": uid,
            "subject": clean_subject,
            "recipient_domain": recipient_domain,
            "date": date_str,
            "tone_type": "sent",
        }],
    )
    return True


def query_sent_similar(query_text: str, n: int = 3) -> list[dict]:
    """
    Find n sent emails most similar to query_text.
    Used during draft generation to inject Mo's own writing voice.
    Returns [] if collection is empty.
    """
    col = _get_collection()
    if col.count() == 0:
        return []

    clean, _ = redact(query_text or "")
    if not clean.strip():
        return []

    results = col.query(
        query_texts=[clean],
        n_results=min(n, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    out = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        out.append({
            "uid": meta.get("uid"),
            "subject": meta.get("subject", ""),
            "recipient_domain": meta.get("recipient_domain", ""),
            "document": results["documents"][0][i],
            "distance": results["distances"][0][i],
        })
    return out


# ---------------------------------------------------------------------------
# Background sync job state
# ---------------------------------------------------------------------------

_job: dict = {
    "running": False,
    "indexed": 0,
    "total": 0,
    "done": False,
    "error": None,
}
_job_lock = threading.Lock()


def get_sync_status() -> dict:
    with _job_lock:
        return {**_job, "collection_count": get_count()}


# ---------------------------------------------------------------------------
# Backfill — indexes full Sent folder incrementally
# ---------------------------------------------------------------------------

def backfill_sent_history(conn) -> dict:
    """
    Index ALL emails in the Sent folder into the `sent_history` ChromaDB collection.

    - Incremental: checks `sent_sync_last_uid` settings row and only processes
      emails with a higher UID than last time. Re-running is cheap.
    - Already-indexed emails are skipped automatically by `index_sent_email`.
    - Updates the `_job` dict throughout so the status endpoint can poll it live.
    - Returns {"indexed": int, "total": int, "collection_count": int}.
    """
    from imap_tools import A
    from backend.email.fetcher import _strip_html
    from backend.email.imap_client import get_mailbox
    from backend.rag.store import _find_sent_folder

    with _job_lock:
        _job.update(running=True, indexed=0, total=0, done=False, error=None)

    try:
        sent_folder = _find_sent_folder(conn)

        # Last UID indexed in a previous run (0 = never run before)
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'sent_sync_last_uid'"
        ).fetchone()
        last_uid = int(row["value"]) if (row and row["value"]) else 0

        # Step 1: fetch headers only to get the UID list quickly (no body download)
        with get_mailbox() as mb:
            mb.folder.set(sent_folder, readonly=True)
            all_headers = list(mb.fetch(
                A(uid=[f"{last_uid + 1}:*"]) if last_uid > 0 else A(all=True),
                mark_seen=False,
                bulk=True,
                headers_only=True,
            ))

        # Sort ascending so we process oldest → newest and the high-watermark is correct
        all_headers.sort(key=lambda m: int(m.uid))
        total = len(all_headers)

        with _job_lock:
            _job["total"] = total

        if total == 0:
            with _job_lock:
                _job.update(running=False, done=True)
            print(f"[sent_store] No new sent emails to index (already up to date).")
            return {"indexed": 0, "total": 0, "collection_count": get_count()}

        print(f"[sent_store] Indexing {total} new sent email(s) from '{sent_folder}'...")

        indexed = 0
        max_uid_indexed = last_uid
        batch_size = 100  # fetch bodies in batches to avoid IMAP timeout

        uid_chunks = [
            [m.uid for m in all_headers[i:i + batch_size]]
            for i in range(0, total, batch_size)
        ]

        for chunk_uids in uid_chunks:
            # Fetch full bodies for this chunk
            with get_mailbox() as mb:
                mb.folder.set(sent_folder, readonly=True)
                full_msgs = list(mb.fetch(
                    A(uid=chunk_uids),
                    mark_seen=False,
                    bulk=True,
                ))

            for msg in full_msgs:
                body = msg.text or _strip_html(msg.html or "")
                if not body.strip():
                    continue

                recipients = ", ".join(str(a) for a in (msg.to or []))
                date_str = msg.date.isoformat() if msg.date else ""
                uid = int(msg.uid)

                try:
                    if index_sent_email(uid, body, msg.subject or "", recipients, date_str):
                        indexed += 1
                        if uid > max_uid_indexed:
                            max_uid_indexed = uid
                except Exception as e:
                    print(f"[sent_store] Failed uid={uid}: {e}")

            with _job_lock:
                _job["indexed"] = indexed

        # Save the high-watermark UID so next run is incremental
        if max_uid_indexed > last_uid:
            conn.execute(
                "INSERT INTO settings(key, value, description) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
                (
                    "sent_sync_last_uid",
                    str(max_uid_indexed),
                    "Highest Sent-folder UID indexed into sent_history ChromaDB",
                ),
            )
            conn.commit()

        print(f"[sent_store] Done. Indexed {indexed} sent email(s). Total in collection: {get_count()}.")

        with _job_lock:
            _job.update(running=False, done=True, indexed=indexed, total=total)

        return {"indexed": indexed, "total": total, "collection_count": get_count()}

    except Exception as e:
        err = str(e)
        print(f"[sent_store] Backfill error: {e}")
        with _job_lock:
            _job.update(running=False, done=True, error=err)
        return {"indexed": 0, "total": 0, "error": err}
