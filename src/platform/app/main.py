from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import a2a_debug, participants, registry, sessions
from app.config import settings
from app.db import engine, init_db
from app.logging_setup import configure_logging
from app.message_bus import close_bus, init_bus
from app.session_service import restore_pending_timeouts


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    await init_db()
    await init_bus()
    await restore_pending_timeouts()
    yield
    await close_bus()
    await engine.dispose()


app = FastAPI(title="Sprint Planning 2.0 Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "log_level": settings.log_level}


app.include_router(registry.router, prefix="/register", tags=["registry"])
app.include_router(participants.router, prefix="/participants", tags=["participants"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(a2a_debug.router, prefix="/a2a", tags=["a2a"])
