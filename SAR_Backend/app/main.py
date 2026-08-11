from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select, text

from app.api.router import api_router
from app.config import get_settings
from app.db import Base, SessionLocal
from app.metrics import MetricsMiddleware, router as metrics_router
from app.middleware import JsonLogMiddleware, RateLimitMiddleware, RequestIdMiddleware
from app.models import Project
from app.storage import ensure_bucket_exists
from pathlib import Path


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    if settings.cors_allow_origins == "*":
        allow_origins = ["*"]
    else:
        allow_origins = [o.strip() for o in settings.cors_allow_origins.split(",")]

    if settings.cors_allow_methods == "*":
        allow_methods = ["*"]
    else:
        allow_methods = [m.strip() for m in settings.cors_allow_methods.split(",")]

    if settings.cors_allow_headers == "*":
        allow_headers = ["*"]
    else:
        allow_headers = [h.strip() for h in settings.cors_allow_headers.split(",")]

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(JsonLogMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    )

    app.include_router(api_router, prefix=settings.api_prefix)
    app.include_router(metrics_router, prefix=settings.metrics_path)

    @app.on_event("startup")
    def _startup():
        if settings.database_url.startswith("sqlite"):
            db = SessionLocal()
            try:
                Base.metadata.create_all(bind=db.get_bind())
                image_columns = {column["name"] for column in inspect(db.get_bind()).get_columns("images")}
                if "frequency_band" not in image_columns:
                    db.execute(text("ALTER TABLE images ADD COLUMN frequency_band TEXT"))
                    db.commit()
            finally:
                db.close()
        ensure_bucket_exists(settings.s3_bucket)
        db = SessionLocal()
        try:
            project = db.scalar(select(Project).where(Project.name == settings.default_project_name))
            if project is None:
                project = Project(name=settings.default_project_name, description="Auto-created default project")
                db.add(project)
                db.commit()
        finally:
            db.close()

    dist_dir = settings.frontend_dist_dir.strip()
    if dist_dir:
        p = Path(dist_dir)
        if p.exists() and p.is_dir():
            app.mount("/", StaticFiles(directory=str(p), html=True), name="frontend")

    return app


app = create_app()
