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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(settings.database_path)
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
