from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database.connection import init_db
from backend.routers import (
    auth,
    contacts,
    customers,
    deals,
    facts,
    history,
    inbox,
    leads,
    prices,
    settings as settings_router,
    style,
    trust,
    usage,
    vendors,
)


def _apply_pending_import():
    """One-time data migration: if an uploaded DB snapshot sits next to the live
    DB as 'agent_import.db', swap it in before anything opens the database.
    Runs before init_db so there is no open connection to corrupt. Idempotent —
    the import file is removed after a successful swap."""
    import os
    import shutil

    db = settings.database_path
    folder = os.path.dirname(db) or "."
    pending = os.path.join(folder, "agent_import.db")

    if not os.path.exists(pending) or os.path.getsize(pending) == 0:
        return

    # Drop any stale WAL/SHM sidecar files of the current DB so SQLite does not
    # try to replay an old write-ahead log against the freshly swapped-in file.
    for ext in ("-wal", "-shm"):
        try:
            os.remove(db + ext)
        except FileNotFoundError:
            pass

    shutil.move(pending, db)
    print(f"[startup] Imported database snapshot applied from {pending} -> {db}")


def _apply_pending_chroma_import():
    """One-time RAG migration: if an uploaded 'chroma_import.tar.gz' sits in the
    data dir, extract it to cleanly replace the chroma_db folder before anything
    opens ChromaDB. Runs at startup so there is no open handle to corrupt.
    Idempotent — the archive is removed after a successful import."""
    import os
    import shutil
    import tarfile

    chroma_path = os.environ.get("CHROMA_PATH", "data/chroma_db")
    parent = os.path.dirname(chroma_path) or "."
    archive = os.path.join(parent, "chroma_import.tar.gz")

    if not os.path.exists(archive) or os.path.getsize(archive) == 0:
        return

    # Clean replace: drop the existing (empty) chroma_db, then extract the
    # uploaded snapshot which contains a top-level 'chroma_db/' folder.
    if os.path.isdir(chroma_path):
        shutil.rmtree(chroma_path, ignore_errors=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(path=parent)
    os.remove(archive)
    print(f"[startup] Imported ChromaDB snapshot from {archive} -> {chroma_path}")


def _seed_password_if_missing():
    """If DASHBOARD_PASSWORD env var is set and DB has no password yet, hash and store it."""
    if not settings.dashboard_password:
        return
    import bcrypt
    from backend.database.connection import get_connection
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='dashboard_password'").fetchone()
        if row and row[0]:
            return  # already set — never overwrite
        hashed = bcrypt.hashpw(settings.dashboard_password.encode(), bcrypt.gensalt(12)).decode()
        conn.execute("UPDATE settings SET value=? WHERE key='dashboard_password'", (hashed,))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _apply_pending_import()
    _apply_pending_chroma_import()
    init_db(settings.database_path)
    _seed_password_if_missing()
    from backend import scheduler
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="AAKE Email Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(facts.router)
app.include_router(customers.router)
app.include_router(deals.router)
app.include_router(history.router)
app.include_router(leads.router)
app.include_router(vendors.router)
app.include_router(settings_router.router)
app.include_router(style.router)
app.include_router(prices.router)
app.include_router(contacts.router)
app.include_router(inbox.router)
app.include_router(trust.router)
app.include_router(usage.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
