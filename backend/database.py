"""SQLAlchemy session/engine setup. Supports SQLite (dev) and Postgres (prod)."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "lotlegends.db"


def _resolve_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{DB_PATH}"
    # Render / Heroku give "postgres://" but SQLAlchemy 2.x wants "postgresql://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # Use the modern psycopg driver name when available; fall back to default
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


DATABASE_URL = _resolve_database_url()

_engine_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Render free Postgres can drop idle connections after a few minutes.
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_recycle"] = 300

engine = create_engine(DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(autoflush=False, autocommit=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_user_legal_columns() -> None:
    """Add consent audit columns to existing deployments (SQLite + Postgres)."""
    insp = inspect(engine)
    if not insp.has_table("users"):
        return
    col_names = {c["name"] for c in insp.get_columns("users")}
    dialect = engine.dialect.name

    with engine.begin() as conn:
        if "terms_privacy_accepted_at" not in col_names:
            if dialect == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN terms_privacy_accepted_at DATETIME"))
            else:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_privacy_accepted_at TIMESTAMP")
                )
        if "legal_documents_version" not in col_names:
            if dialect == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN legal_documents_version VARCHAR(32)"))
            else:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN IF NOT EXISTS legal_documents_version VARCHAR(32)")
                )


def init_db() -> None:
    """Create all tables. Imported here to avoid circular imports at module load."""
    from . import models  # noqa: F401  – ensures models register on Base
    Base.metadata.create_all(bind=engine)
    _ensure_user_legal_columns()
