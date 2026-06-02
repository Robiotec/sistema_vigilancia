from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routes import admin, arcom, auth, mediamtx, osint, streams, telemetry
from app.core.config import get_settings
from app.db.session import Base, SessionLocal, engine
from app.models import entities  # noqa: F401
from app.services.auth_service import ensure_master_user
import app.services.stream_service as stream_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_master_user(db, settings.master_username, settings.master_password)
    finally:
        db.close()
    yield
    if stream_service._mediamtx_client is not None:
        await stream_service._mediamtx_client.aclose()


app = FastAPI(title="Robiotec API Central", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(streams.router)
app.include_router(mediamtx.router)
app.include_router(telemetry.router)
app.include_router(arcom.router)
app.include_router(osint.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
