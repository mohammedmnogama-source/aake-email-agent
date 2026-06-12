"""
backend/rag/approved_store.py — Learning store for approved drafts.

Every time Mo approves a draft (with or without editing), it gets indexed here.
This is a SEPARATE ChromaDB collection from the emails collection.

The emails collection answers: "what past emails look like this one?"
This collection answers: "what did Mo actually write for similar emails?"

Two functions:
  index_approved_draft()    — called on every approval
  query_approved_examples() — called when building the AI prompt for a new email
"""

import os
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from backend.ai.redactor import redact

# Same folder as the emails collection — ChromaDB stores multiple collections in one folder
_CHROMA_PATH = os.environ.get("CHROMA_PATH", "data/chroma_db")

# Separate collection name from the emails one ("emails")
_COLLECTION_NAME = "approved_drafts"

_client = None
_collection = None


def _get_collection():
    """Returns the approved_drafts ChromaDB collection, creating it if needed."""
    global _client, _collection
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


def index_approved_draft(
    draft_id: int,
    subject: str,
    from_name: str,
    category: str,
    approved_content: str,
    was_edited: int,
) -> None:
    """
    Save an approved draft to ChromaDB so future emails can learn from it.

    - draft_id is the primary key from the approved_drafts SQLite table
    - approved_content is what Mo actually approved (after any edits)
    - was_edited = 1 means Mo changed Claude's suggestion (more valuable for learning)
    """
    col = _get_collection()

    chroma_id = f"draft_{draft_id}"

    # Don't index empty drafts
    if not approved_content or not approved_content.strip():
        return

    # Redact PII from the content before storing
    clean_content, _ = redact(approved_content)
    clean_subject, _ = redact(subject or "")

    # The document ChromaDB embeds for similarity search
    # We include the subject so searching by subject also works
    document = f"Subject: {clean_subject}\n\nApproved reply:\n{clean_content}".strip()

    col.add(
        ids=[chroma_id],
        documents=[document],
        metadatas=[{
            "draft_id":    draft_id,
            "subject":     clean_subject,
            "from_name":   from_name or "",
            "category":    category or "",
            "was_edited":  was_edited,
        }],
    )
    print(f"[approved_store] Indexed approved draft {draft_id} (edited={was_edited})")


def query_approved_examples(subject: str, body_preview: str, n: int = 3) -> list[dict]:
    """
    Find the n most similar approved drafts for a given incoming email.

    Returns a list of dicts:
      [
        {
          "subject": "Re: Cisco switches quote",
          "category": "lead",
          "was_edited": 0,
          "approved_content": "Dear ...\n\nThank you for...",
          "distance": 0.15,
        },
        ...
      ]

    Returns [] if collection is empty (no approvals yet — normal on first run).
    """
    col = _get_collection()

    if col.count() == 0:
        return []

    # Build query text from the incoming email's subject + preview
    clean_subject, _ = redact(subject or "")
    clean_body, _ = redact(body_preview or "")
    query_text = f"Subject: {clean_subject}\n\n{clean_body}".strip()

    if not query_text:
        return []

    results = col.query(
        query_texts=[query_text],
        n_results=min(n, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    examples = []
    for i, doc_id in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i]
        doc  = results["documents"][0][i]

        # Extract just the approved reply part (after "Approved reply:\n")
        approved_content = doc
        if "Approved reply:\n" in doc:
            approved_content = doc.split("Approved reply:\n", 1)[1].strip()

        examples.append({
            "subject":          meta.get("subject", ""),
            "category":         meta.get("category", ""),
            "was_edited":       meta.get("was_edited", 0),
            "approved_content": approved_content,
            "distance":         results["distances"][0][i],
        })

    return examples
