"""
Database connection and session management.
Production-ready for Docker: waits for DB DNS/TCP/SQLAlchemy connect.
"""
import os
import time
import socket
import urllib.parse
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError

from .models import Base


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/vide_gen"
)

DEBUG_SQL = os.getenv("DEBUG", "false").lower() == "true"

# How long to wait for DB on container startup
DB_WAIT_RETRIES = int(os.getenv("DB_WAIT_RETRIES", "30"))   # 30 attempts
DB_WAIT_DELAY = float(os.getenv("DB_WAIT_DELAY", "2"))      # 2 sec between attempts


def _wait_for_dns_and_tcp(url: str, retries: int, delay: float) -> None:
    """
    Wait until hostname can be resolved and TCP connection can be established.
    This fixes transient Docker DNS resolution issues ("Temporary failure in name resolution").
    """
    u = urllib.parse.urlparse(url)
    host = u.hostname
    port = u.port or 5432

    if not host:
        raise RuntimeError("DATABASE_URL has no hostname")

    last_err = None
    for i in range(1, retries + 1):
        try:
            # 1) DNS resolve
            socket.getaddrinfo(host, port)

            # 2) TCP connect
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((host, port))
            s.close()

            print(f"✅ DB network ready: {host}:{port}")
            return
        except Exception as e:
            last_err = e
            print(f"⏳ Waiting for DB network ({i}/{retries}) {host}:{port} -> {e}")
            time.sleep(delay)

    raise RuntimeError(f"❌ DB network not ready after {retries} tries: {last_err}")


def _create_engine_with_retry(url: str, retries: int, delay: float):
    """
    Create SQLAlchemy engine and verify we can execute a simple query.
    """
    # First: wait for DNS + TCP
    _wait_for_dns_and_tcp(url, retries=retries, delay=delay)

    last_err = None
    for i in range(1, retries + 1):
        try:
            engine = create_engine(
                url,
                pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
                max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "0")),
                pool_pre_ping=True,
                echo=DEBUG_SQL,
            )

            # Verify DB is actually accepting connections
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✅ DB SQLAlchemy connect OK")
            return engine
        except OperationalError as e:
            last_err = e
            print(f"⏳ Waiting for DB SQLAlchemy ({i}/{retries}) -> {e}")
            time.sleep(delay)

    raise RuntimeError(f"❌ DB not ready for SQLAlchemy after {retries} tries: {last_err}")


# Create engine on import (safe now, because we wait)
engine = _create_engine_with_retry(
    DATABASE_URL,
    retries=DB_WAIT_RETRIES,
    delay=DB_WAIT_DELAY,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables() -> None:
    """
    Create all database tables.
    In Docker, tables creation may be called on startup; we keep it safe.
    """
    # Extra safety: in case create_tables is called before engine is fully ok
    for i in range(1, DB_WAIT_RETRIES + 1):
        try:
            Base.metadata.create_all(bind=engine)
            print("✅ Tables ensured (create_all)")
            return
        except OperationalError as e:
            print(f"⏳ create_all failed ({i}/{DB_WAIT_RETRIES}) -> {e}")
            time.sleep(DB_WAIT_DELAY)
    raise RuntimeError("❌ Could not create tables after retries")


def drop_tables() -> None:
    """Drop all database tables (for testing)."""
    Base.metadata.drop_all(bind=engine)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Get a database session with automatic cleanup.
    Usage:
        with get_db_session() as db:
            ...
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency:
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
