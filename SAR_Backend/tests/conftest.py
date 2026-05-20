from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config as app_config
from app.db import Base
from app.models import Project


@pytest.fixture(scope="session")
def engine():
    e = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=e)
    return e


@pytest.fixture()
def db_session(engine, monkeypatch):
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    monkeypatch.setattr("app.db.SessionLocal", SessionLocal, raising=False)
    monkeypatch.setattr("app.workers.tasks.SessionLocal", SessionLocal, raising=False)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.storage.ensure_bucket_exists", lambda *_args, **_kwargs: None, raising=False)

    app_config._settings = None
    settings = app_config.get_settings()
    settings.database_url = "sqlite+pysqlite:///:memory:"
    settings.redis_url = "redis://localhost:6379/0"
    settings.upload_tmp_dir = str(tmp_path / "uploads")

    project = db_session.query(Project).filter(Project.name == settings.default_project_name).first()
    if project is None:
        db_session.add(Project(id=uuid.uuid4(), name=settings.default_project_name, description="default"))
    db_session.commit()

    from app.main import create_app

    app = create_app()
    return TestClient(app)
