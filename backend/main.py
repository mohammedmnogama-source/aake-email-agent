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
