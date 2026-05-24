from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from watcher.config import load_config


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _normalize_db_url(url: str) -> str:
    """Railway's Postgres DATABASE_URL starts with 'postgresql://' (no driver
    prefix). SQLAlchemy 2 needs an explicit driver, so we patch it in."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def get_engine():
    global _engine
    if _engine is None:
        cfg = load_config()
        _engine = create_engine(_normalize_db_url(cfg.secrets.database_url), future=True, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), future=True, expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
