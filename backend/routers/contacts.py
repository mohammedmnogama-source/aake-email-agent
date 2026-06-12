import threading

from fastapi import APIRouter, Depends

from backend.database.connection import get_connection, init_db
from backend.middleware.auth import require_auth
from backend.config import settings
from backend.email.contact_scanner import scan_contacts, search_contacts, list_all_contacts

router = APIRouter(prefix="/api/contacts", tags=["contacts"], dependencies=[Depends(require_auth)])

_job = {"running": False, "total": 0, "folder": "", "done": False, "error": None}
_lock = threading.Lock()


def _run_scan():
    with _lock:
        _job.update(running=True, total=0, folder="", done=False, error=None)

    def cb(total, folder):
        with _lock:
            _job["total"] = total
            _job["folder"] = folder

    try:
        init_db(settings.database_path)
        conn = get_connection()
        scan_contacts(conn, progress_cb=cb)
        conn.close()
        with _lock:
            _job.update(running=False, done=True)
    except Exception as e:
        with _lock:
            _job.update(running=False, done=True, error=str(e))


@router.post("/scan")
def start_scan():
    with _lock:
        if _job["running"]:
            return {"started": False, "reason": "already running"}
    t = threading.Thread(target=_run_scan, daemon=True)
    t.start()
    return {"started": True}


@router.get("/scan/status")
def scan_status():
    with _lock:
        return dict(_job)


@router.get("/search")
def search(q: str = "", limit: int = 10):
    conn = get_connection()
    if not q:
        results = list_all_contacts(conn, limit=limit)
    else:
        results = search_contacts(conn, q, limit=limit)
    conn.close()
    return results


@router.get("")
def list_contacts(limit: int = 500):
    conn = get_connection()
    results = list_all_contacts(conn, limit=limit)
    conn.close()
    return results
