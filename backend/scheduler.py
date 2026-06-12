from apscheduler.schedulers.background import BackgroundScheduler

from backend.database.connection import get_connection
from backend.email.fetcher import fetch_new_emails

_scheduler = BackgroundScheduler()

# Tracks whether the one-time backfill (indexing old emails to ChromaDB) has run
_backfill_done = False


def _poll_job():
    """
    Runs every N minutes:
    1. Fetch new emails from IMAP
    2. Analyze any pending ones
    """
    from backend import sync_tracker
    if sync_tracker.get()["running"]:
        return  # manual sync already in progress — skip this tick

    try:
        sync_tracker.start()
        new_ids = fetch_new_emails()
        from backend.ai.analyzer import analyze_pending
        analyzed_ids = analyze_pending()
        sync_tracker.finish(len(new_ids), len(analyzed_ids))
        if new_ids:
            print(f"[scheduler] Fetched {len(new_ids)} and analyzed {len(analyzed_ids)} email(s)")
    except Exception as e:
        sync_tracker.fail(str(e))
        print(f"[scheduler] Poll error: {e}")


def _analyze_job():
    """
    Runs the AI analyzer on all pending emails.
    Called right after a fetch that returned new emails.
    """
    try:
        from backend.ai.analyzer import analyze_pending
        ids = analyze_pending()
        if ids:
            print(f"[scheduler] Analyzed {len(ids)} email(s)")
    except Exception as e:
        print(f"[scheduler] Analyze error: {e}")


def _rag_backfill_job():
    """
    One-time job that runs once on startup.
    Indexes all existing emails (and sent folder) to ChromaDB so that
    RAG has historical context from day one.

    Safe to call multiple times — already-indexed emails are skipped.
    """
    global _backfill_done
    if _backfill_done:
        return

    _backfill_done = True
    print("[scheduler] Starting RAG backfill (indexing existing emails to ChromaDB)...")

    try:
        from backend.rag.store import backfill_existing_emails, backfill_sent_folder
        conn = get_connection()
        try:
            inbox_count = backfill_existing_emails(conn)
            sent_count = backfill_sent_folder(conn)
            print(f"[scheduler] RAG backfill complete — {inbox_count} inbox + {sent_count} sent emails indexed")
        finally:
            conn.close()
    except Exception as e:
        print(f"[scheduler] RAG backfill error: {e}")


def _followup_chaser_job():
    """
    Runs once daily (8 AM Kuwait time = 5 AM UTC).
    Finds un-replied customer contacts and creates follow-up draft suggestions.
    """
    try:
        from backend.email.followup_chaser import run_followup_chaser
        conn = get_connection()
        try:
            n = run_followup_chaser(conn)
            if n:
                print(f"[scheduler] Follow-up chaser created {n} suggestion(s)")
        finally:
            conn.close()
    except Exception as e:
        print(f"[scheduler] Follow-up chaser error: {e}")


def start():
    interval = _get_interval()
    _scheduler.add_job(_poll_job, "interval", minutes=interval, id="poll_job", replace_existing=True)

    # Daily follow-up chaser at 8 AM Kuwait time (UTC+3 = 05:00 UTC)
    _scheduler.add_job(
        _followup_chaser_job, "cron",
        hour=5, minute=0,
        id="followup_chaser", replace_existing=True,
        misfire_grace_time=3600,
    )

    # Run the one-time backfill 10 seconds after startup (gives the server time to fully start)
    _scheduler.add_job(_rag_backfill_job, "date", id="rag_backfill", misfire_grace_time=60)

    _scheduler.start()
    print(f"[scheduler] Started, polling every {interval} min")


def stop():
    _scheduler.shutdown(wait=False)


def update_interval(minutes: int):
    _scheduler.reschedule_job("poll_job", trigger="interval", minutes=minutes)


def _get_interval() -> int:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'poll_interval_min'"
        ).fetchone()
        conn.close()
        return int(row["value"]) if row else 15
    except Exception:
        return 15
