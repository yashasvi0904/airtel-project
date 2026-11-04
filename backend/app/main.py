"""FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from . import models
from .config import get_settings
from .db import Base, SessionLocal, engine
from .routers import admin, journeys, orders, public
from .security import hash_password
from .services.catalogue import seed_catalogue
from .services.kyc.service import purge_expired

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def init_db():
    s = get_settings()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    if s.database_url.startswith("sqlite"):
        from pathlib import Path

        Path(s.database_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_catalogue(db)
        if not db.scalar(select(models.User).where(models.User.email == s.admin_email)):
            db.add(models.User(email=s.admin_email, name="Accel Admin", password_hash=hash_password(s.admin_password), role="admin"))
            db.commit()
        n = purge_expired(db)
        if n:
            log.info("purged %s expired KYC documents", n)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title=s.app_name, version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",")], allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        msgs = [f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}".strip(": ") for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": "; ".join(msgs) or "Invalid request"})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)  # message only; request bodies are never logged
        return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again."})

    for r in (public.router, journeys.router, orders.router, admin.router):
        app.include_router(r)
    return app


app = create_app()
