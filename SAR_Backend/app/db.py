from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def create_session_factory() -> sessionmaker[Session]:
    settings = get_settings()
    db_url = settings.database_url
    is_sqlite = db_url.startswith("sqlite")
    engine = create_engine(
        db_url,
        pool_pre_ping=not is_sqlite,
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _sqlite_register_functions(dbapi_connection, _):
            # Keep schema check constraints portable for standalone SQLite mode.
            dbapi_connection.create_function("btrim", 1, lambda v: (v or "").strip())
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


SessionLocal = create_session_factory()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
