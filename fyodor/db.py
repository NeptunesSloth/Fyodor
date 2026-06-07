"""Database setup: SQLAlchemy engine + session, SQLite by default.

Upgrade path to Postgres is just an env var: set ``FYODOR_DATABASE_URL`` to a
``postgresql+psycopg://...`` URL.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    url = os.getenv("FYODOR_DATABASE_URL")
    if url:
        return url
    Path("state").mkdir(exist_ok=True)
    return "sqlite:///state/fyodor.db"


_engine = None
_SessionFactory: sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        url = database_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, echo=False, future=True, connect_args=connect_args)
    return _engine


def init_db() -> None:
    """Create all tables. Safe to call repeatedly (acts as a simple migration)."""
    from . import models  # noqa: F401 - ensure models are registered

    Base.metadata.create_all(get_engine())


def get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionFactory


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
