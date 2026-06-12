"""
backend/sync_tracker.py — thread-safe sync status store.

The sync endpoint runs in a background thread. The frontend polls
GET /api/inbox/sync-status to get live progress updates.
"""
import threading
from datetime import datetime, timezone

_lock = threading.Lock()

_status: dict = {
    "running": False,
    "stage": "idle",       # idle | fetching | analyzing | done | error
    "message": "Ready",
    "current": 0,
    "total": 0,
    "fetched": 0,
    "analyzed": 0,
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def get() -> dict:
    with _lock:
        return dict(_status)


def _update(**kwargs) -> None:
    with _lock:
        _status.update(kwargs)


def start() -> None:
    _update(
        running=True,
        stage="fetching",
        message="Connecting to inbox...",
        current=0,
        total=0,
        fetched=0,
        analyzed=0,
        error=None,
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=None,
    )


def set_fetching(count: int) -> None:
    if count == 0:
        _update(message="No new emails found — moving to analysis...")
    else:
        _update(
            stage="fetching",
            message=f"Fetched {count} new email(s) — starting analysis...",
            fetched=count,
            total=count,
        )


def set_analyzing(current: int, total: int, subject: str = "") -> None:
    label = f'"{subject[:50]}"' if subject else f"email {current}"
    _update(
        stage="analyzing",
        message=f"Analyzing {current} of {total}: {label}",
        current=current,
        total=total,
    )


def finish(fetched: int, analyzed: int) -> None:
    if analyzed == 0 and fetched == 0:
        msg = "No new emails."
    else:
        msg = f"Done — {fetched} fetched, {analyzed} analyzed."
    _update(
        running=False,
        stage="done",
        message=msg,
        fetched=fetched,
        analyzed=analyzed,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )


def fail(error_msg: str) -> None:
    _update(
        running=False,
        stage="error",
        message=f"Error: {error_msg}",
        error=error_msg,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
