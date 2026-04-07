"""Database engine, session factory, and initialization utilities."""

import logging

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import configure_logging, settings
from db_models import Base

configure_logging()
logger = logging.getLogger(__name__)


def _get_dsn(db_name: str | None = None) -> str:
    """Build a psycopg2-compatible SQLAlchemy DSN."""
    name = db_name or settings.DB_NAME
    return (
        f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{name}"
    )


def ensure_database_exists() -> None:
    """Create the target database if it doesn't exist.

    Uses a raw psycopg2 connection to the system 'postgres' database because
    ``CREATE DATABASE`` cannot run inside a transaction — which SQLAlchemy
    always starts by default.
    """
    conn = None
    try:
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dbname="postgres",
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (settings.DB_NAME,)
            )
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{settings.DB_NAME}"')
                logger.info("Database '%s' created.", settings.DB_NAME)
            else:
                logger.debug("Database '%s' already exists.", settings.DB_NAME)
    except Exception as exc:
        logger.error("Failed to ensure database exists: %s", exc)
        raise
    finally:
        if conn:
            conn.close()


def create_db_engine():
    """Create and return a SQLAlchemy engine."""
    return create_engine(_get_dsn(), echo=False, pool_pre_ping=True)


# Module-level engine and session factory (initialized on first import of init_db)
_engine = None
_SessionLocal: sessionmaker | None = None


def init_db() -> None:
    """Initialize database: ensure it exists, create tables, set up session factory."""
    global _engine, _SessionLocal

    ensure_database_exists()

    _engine = create_db_engine()
    # Create all tables that don't exist yet (safe to call multiple times)
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=True, autocommit=False)
    logger.info("Database initialized.")


def get_session() -> Session:
    """Return a new SQLAlchemy session. Caller is responsible for closing it."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()
